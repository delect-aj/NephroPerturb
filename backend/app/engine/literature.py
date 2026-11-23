"""Biomedical literature (Europe PMC + NCBI PubMed fallback) & ClinicalTrials.gov v2 client.

Zero extra third-party dependencies (uses Python stdlib urllib + xml.etree.ElementTree).
Results are cached for 7 days in SQLite (agent_state.db) with a 300s soft circuit
breaker when Europe PMC is unreachable so queries switch seamlessly to PubMed.
"""
import hashlib
import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from ..state_db import connect_state_db, prune_table_if_needed, write_lock

CACHE_TTL_SEC = 7 * 24 * 3600.0
MAX_CACHE_ROWS = 5000
EPMC_COOLDOWN_SEC = 300.0
USER_AGENT = "NephroPerturb/1.2 (kidney drug repurposing research agent)"

_CB_LOCK = threading.Lock()
_EPMC_FAIL_UNTIL = 0.0
_PUBMED_RATE_LOCK = threading.Lock()
_LAST_PUBMED_TS = 0.0

RENAL_DISEASE_TERMS = {
    "dkd": '"diabetic kidney disease" OR "diabetic nephropathy" OR "diabetic glomerulopathy"',
    "diabetic": '"diabetic kidney disease" OR "diabetic nephropathy"',
    "dn": '"diabetic kidney disease" OR "diabetic nephropathy"',
    "ln": '"lupus nephritis"',
    "lupus": '"lupus nephritis"',
    "igan": '"IgA nephropathy"',
    "aki": '"acute kidney injury" OR "renal ischemia"',
    "ckd": '"chronic kidney disease" OR "renal fibrosis" OR "kidney fibrosis"',
    "fsgs": '"focal segmental glomerulosclerosis"',
    "fibrosis": '"renal fibrosis" OR "kidney fibrosis" OR "tubulointerstitial fibrosis"',
    "podocyte": '"podocyte" OR "glomerular disease" OR "proteinuria"',
    "tubule": '"renal tubular" OR "proximal tubule" OR "tubular injury"',
    "default": '"kidney disease" OR "renal fibrosis" OR "nephropathy" OR "glomerular" OR "diabetic kidney"',
}

SAFETY_QUERY_TERMS = (
    '"nephrotoxicity" OR "acute kidney injury" OR "drug-induced kidney injury" '
    'OR "renal toxicity" OR "tubulotoxicity"'
)

_CLINICAL_RE = re.compile(
    r"\b(randomized|randomised|clinical trial|phase\s*[i1v234]+|placebo[- ]controlled|"
    r"cohort study|multicenter|retrospective|patients with|egfr|albuminuria)\b",
    re.I,
)
_PRECLINICAL_RE = re.compile(
    r"\b(mice|mouse|rat|rats|murine|db/db|stz|streptozotocin|uuo|unilateral ureteral|"
    r"in vivo|xenograft|zebrafish|nephrectomy)\b",
    re.I,
)
_SAFETY_RE = re.compile(
    r"\b(nephrotoxic\w*|nephrotoxicity|acute kidney injury|drug-induced kidney|"
    r"tubular necrosis|renal failure|tubulotoxicity|calcineurin inhibitor toxicity)\b",
    re.I,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_CONCLUSION_SEC_RE = re.compile(
    r"(?:^|\b)(?:CONCLUSIONS?|FINDINGS?|INTERPRETATION)\s*[:\-–]\s*(.+)$",
    re.I,
)
_RESULTS_SEC_RE = re.compile(
    r"(?:^|\b)RESULTS?\s*[:\-–]\s*(.+?)(?=(?:\bCONCLUSIONS?\s*[:\-–]|\bLIMITATIONS?\s*[:\-–]|$))",
    re.I,
)
_OUTCOME_SENT_RE = re.compile(
    r"\b(demonstrat\w*|showed|reduced|attenuat\w*|ameliorat\w*|improv\w*|inhibit\w*|"
    r"protect\w*|prevent\w*|induc\w*|caus\w*|associat\w*|nephrotox\w*|significant\w*|"
    r"preserved|decreased|increased|suppressed|randomized|trial|patients|suggest\w*|conclud\w*)\b",
    re.I,
)


def reset_circuit_breakers() -> None:
    """Reset provider circuit breakers (used in tests)."""
    global _EPMC_FAIL_UNTIL
    with _CB_LOCK:
        _EPMC_FAIL_UNTIL = 0.0


def _epmc_timeout() -> float:
    try:
        return max(1.0, float(os.environ.get("EUROPEPMC_TIMEOUT", "4.5")))
    except ValueError:
        return 4.5


def _strip_text(raw: str | None, max_len: int = 240) -> str:
    if not raw:
        return ""
    clean = _WS_RE.sub(" ", _TAG_RE.sub(" ", str(raw))).strip()
    if len(clean) <= max_len:
        return clean
    return clean[: max_len - 1].rstrip() + "…"


def _extract_takeaway(raw_abstract: str | None, title: str = "", max_len: int = 220) -> str:
    """Extract Results/Conclusions or key outcome sentence instead of opening background."""
    clean = _WS_RE.sub(" ", _TAG_RE.sub(" ", str(raw_abstract or ""))).strip()
    if not clean:
        return _strip_text(title, max_len)

    m_con = _CONCLUSION_SEC_RE.search(clean)
    if m_con and len(m_con.group(1).strip()) >= 25:
        return _strip_text(m_con.group(1), max_len)

    m_res = _RESULTS_SEC_RE.search(clean)
    if m_res and len(m_res.group(1).strip()) >= 25:
        return _strip_text(m_res.group(1), max_len)

    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean) if len(s.strip()) >= 25]
    if len(sents) >= 2:
        half = sents[len(sents) // 2 :]
        scored = [s for s in reversed(half) if _OUTCOME_SENT_RE.search(s)]
        if scored:
            return _strip_text(scored[0], max_len)
        any_scored = [s for s in reversed(sents) if _OUTCOME_SENT_RE.search(s)]
        if any_scored:
            return _strip_text(any_scored[0], max_len)
        return _strip_text(sents[-1], max_len)
    return _strip_text(clean, max_len)


def _expand_disease_terms(disease_context: str | None) -> str:
    ctx = (disease_context or "").strip().lower()
    if not ctx:
        return RENAL_DISEASE_TERMS["default"]
    for key, expr in RENAL_DISEASE_TERMS.items():
        if key != "default" and key in ctx:
            return expr
    safe_ctx = re.sub(r'["\n\r]+', " ", ctx).strip()
    if len(safe_ctx) > 4 and "kidney" not in safe_ctx and "renal" not in safe_ctx:
        return f'"{safe_ctx}" OR {RENAL_DISEASE_TERMS["default"]}'
    return f'"{safe_ctx}"'


def _http_get(url: str, timeout: float = 8.0) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json, application/xml;q=0.9, */*;q=0.8",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _classify_paper(paper: dict, is_safety_query: bool = False) -> str:
    title = paper.get("title") or ""
    snippet = paper.get("snippet") or ""
    pub_type = " ".join(paper.get("pub_types") or [])
    blob = f"{title} {snippet}"

    if is_safety_query and _SAFETY_RE.search(blob):
        return "Safety Warning"
    if _SAFETY_RE.search(title) and not re.search(r"\bprotect\w*|\battenuat\w*|\baméliorat\w*|\bameliorat\w*|\btreatment\b", title, re.I):
        return "Safety Warning"
    if "review" in pub_type.lower() and not _CLINICAL_RE.search(title):
        return "Review"
    if "clinical trial" in pub_type.lower() or _CLINICAL_RE.search(blob):
        return "Clinical"
    if _PRECLINICAL_RE.search(blob):
        return "Preclinical"
    if is_safety_query:
        return "Safety Warning"
    return "Mechanistic"


def _query_europepmc(query: str, max_results: int = 4, timeout: float | None = None) -> dict:
    """Query Europe PMC REST search API with circuit breaker."""
    global _EPMC_FAIL_UNTIL
    now = time.time()
    with _CB_LOCK:
        if now < _EPMC_FAIL_UNTIL:
            raise ConnectionError("Europe PMC circuit breaker active")

    t_out = timeout if timeout is not None else _epmc_timeout()
    params = urllib.parse.urlencode({
        "query": query,
        "format": "json",
        "resultType": "core",
        "pageSize": str(max(1, min(10, int(max_results)))),
        "sort": "CITED desc",
    })
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?{params}"
    try:
        raw = _http_get(url, timeout=t_out)
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except Exception as exc:
        with _CB_LOCK:
            _EPMC_FAIL_UNTIL = time.time() + EPMC_COOLDOWN_SEC
        raise ConnectionError(f"Europe PMC error: {exc}") from exc

    hit_count = int(data.get("hitCount") or 0)
    results = (data.get("resultList") or {}).get("result") or []
    papers = []
    for r in results:
        pmid = str(r.get("pmid") or "").strip()
        pmcid = str(r.get("pmcid") or "").strip()
        doi = str(r.get("doi") or "").strip()
        if not (pmid or pmcid or doi):
            continue
        jinfo = (r.get("journalInfo") or {}).get("journal") or {}
        journal = r.get("journalTitle") or jinfo.get("medlineAbbreviation") or jinfo.get("title") or ""
        pub_types = (r.get("pubTypeList") or {}).get("pubType") or []
        if isinstance(pub_types, str):
            pub_types = [pub_types]
        if pmid:
            link = f"https://europepmc.org/article/MED/{pmid}"
        elif pmcid:
            link = f"https://europepmc.org/article/PMC/{pmcid}"
        else:
            link = f"https://doi.org/{doi}"
        clean_title = _strip_text(r.get("title"), 220)
        takeaway = _extract_takeaway(r.get("abstractText"), title=clean_title, max_len=220)
        papers.append({
            "pmid": pmid or None,
            "pmcid": pmcid or None,
            "doi": doi or None,
            "title": clean_title,
            "journal": _strip_text(journal, 80),
            "year": str(r.get("pubYear") or ""),
            "authors": _strip_text(r.get("authorString"), 90),
            "cited_by": int(r.get("citedByCount") or 0),
            "pub_types": [str(x) for x in pub_types[:4]],
            "takeaway": takeaway,
            "snippet": takeaway,
            "url": link,
            "source": "europepmc",
        })
    return {"total_hits": hit_count, "papers": papers, "provider": "europepmc"}


def _throttle_pubmed() -> None:
    """Respect NCBI's unauthenticated 3 req/s rate guideline cleanly."""
    global _LAST_PUBMED_TS
    if os.environ.get("NCBI_API_KEY", "").strip():
        return
    with _PUBMED_RATE_LOCK:
        elapsed = time.time() - _LAST_PUBMED_TS
        if elapsed < 0.36:
            time.sleep(0.36 - elapsed)
        _LAST_PUBMED_TS = time.time()


def _query_pubmed(query: str, max_results: int = 4, timeout: float = 8.0) -> dict:
    """Fallback to NCBI PubMed E-utilities (esearch + efetch XML)."""
    api_key = os.environ.get("NCBI_API_KEY", "").strip()
    es_params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": str(max(1, min(10, int(max_results)))),
        "sort": "relevance",
    }
    if api_key:
        es_params["api_key"] = api_key
    _throttle_pubmed()
    es_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?{urllib.parse.urlencode(es_params)}"
    es_data = json.loads(_http_get(es_url, timeout=timeout).decode("utf-8", errors="replace"))
    es_res = es_data.get("esearchresult") or {}
    total_hits = int(es_res.get("count") or 0)
    id_list = [str(x).strip() for x in (es_res.get("idlist") or []) if str(x).strip()]
    if not id_list:
        return {"total_hits": total_hits, "papers": [], "provider": "pubmed"}

    ef_params = {"db": "pubmed", "id": ",".join(id_list), "retmode": "xml"}
    if api_key:
        ef_params["api_key"] = api_key
    _throttle_pubmed()
    ef_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?{urllib.parse.urlencode(ef_params)}"
    xml_bytes = _http_get(ef_url, timeout=timeout)
    root = ET.fromstring(xml_bytes)

    papers = []
    for art in root.findall(".//PubmedArticle"):
        pmid = (art.findtext(".//MedlineCitation/PMID") or "").strip()
        if not pmid:
            continue
        title_el = art.find(".//Article/ArticleTitle")
        title = "".join(title_el.itertext()) if title_el is not None else ""
        journal = (
            art.findtext(".//Article/Journal/ISOAbbreviation")
            or art.findtext(".//MedlineJournalInfo/MedlineTA")
            or ""
        )
        year = (
            art.findtext(".//Article/Journal/JournalIssue/PubDate/Year")
            or (art.findtext(".//Article/Journal/JournalIssue/PubDate/MedlineDate") or "")[:4]
        )
        authors_list = []
        for au in art.findall(".//Article/AuthorList/Author")[:3]:
            ln = (au.findtext("LastName") or "").strip()
            ini = (au.findtext("Initials") or "").strip()
            if ln:
                authors_list.append(f"{ln} {ini}".strip())
        author_str = ", ".join(authors_list)
        if len(art.findall(".//Article/AuthorList/Author")) > 3:
            author_str += " et al."

        pub_types = [
            (pt.text or "").strip()
            for pt in art.findall(".//Article/PublicationTypeList/PublicationType")
            if (pt.text or "").strip()
        ]
        doi = ""
        pmcid = ""
        for aid in art.findall(".//PubmedData/ArticleIdList/ArticleId"):
            itype = aid.attrib.get("IdType", "")
            val = (aid.text or "").strip()
            if itype == "doi" and not doi:
                doi = val
            elif itype == "pmc" and not pmcid:
                pmcid = val
        abs_parts = []
        for ab in art.findall(".//Article/Abstract/AbstractText"):
            txt = "".join(ab.itertext()).strip()
            if not txt:
                continue
            lbl = (ab.attrib.get("Label") or ab.attrib.get("NlmCategory") or "").strip()
            abs_parts.append(f"{lbl}: {txt}" if lbl and not txt.upper().startswith(lbl.upper()) else txt)
        clean_title = _strip_text(title, 220)
        takeaway = _extract_takeaway(" ".join(abs_parts), title=clean_title, max_len=220)
        papers.append({
            "pmid": pmid,
            "pmcid": pmcid or None,
            "doi": doi or None,
            "title": clean_title,
            "journal": _strip_text(journal, 80),
            "year": str(year or ""),
            "authors": _strip_text(author_str, 90),
            "cited_by": None,
            "pub_types": pub_types[:4],
            "takeaway": takeaway,
            "snippet": takeaway,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "source": "pubmed",
        })
    return {"total_hits": total_hits, "papers": papers, "provider": "pubmed"}


def _run_lit_query(query: str, max_results: int) -> dict:
    epmc_err = None
    try:
        return _query_europepmc(query, max_results=max_results)
    except Exception as exc:
        epmc_err = str(exc)

    try:
        res = _query_pubmed(query, max_results=max_results)
        res["fallback_from"] = f"europepmc ({epmc_err[:80]})"
        return res
    except Exception as pub_exc:
        return {
            "total_hits": 0,
            "papers": [],
            "provider": "unavailable",
            "error": f"Europe PMC & PubMed unavailable: {pub_exc}"[:180],
        }


def _cache_get(cache_key: str) -> dict | None:
    now = time.time()
    con = connect_state_db()
    try:
        row = con.execute(
            "SELECT payload_json, created_at FROM literature_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    finally:
        con.close()
    if not row:
        return None
    payload_json, created_at = row
    if now - float(created_at) > CACHE_TTL_SEC:
        return None
    try:
        data = json.loads(payload_json)
        data["cached"] = True
        return data
    except Exception:
        return None


def _cache_set(cache_key: str, source: str, payload: dict) -> None:
    now = time.time()
    to_save = dict(payload)
    to_save.pop("cached", None)
    raw = json.dumps(to_save, ensure_ascii=False)
    with write_lock():
        con = connect_state_db()
        try:
            con.execute(
                "INSERT OR REPLACE INTO literature_cache (cache_key, source, payload_json, created_at) "
                "VALUES (?, ?, ?, ?)",
                (cache_key, source, raw, now),
            )
            prune_table_if_needed(con, "literature_cache", "created_at", CACHE_TTL_SEC, MAX_CACHE_ROWS)
            con.commit()
        finally:
            con.close()


def _overall_evidence_tier(eff_hits: int, safe_hits: int, papers: list[dict], provider: str) -> str:
    if provider == "unavailable" and not papers:
        return "Unverified (literature API unreachable)"
    eff_cats = {p["category"] for p in papers if p.get("query_role") == "efficacy"}
    if "Clinical" in eff_cats:
        return "Clinical"
    if "Preclinical" in eff_cats:
        return "Preclinical"
    if eff_hits > 0 or eff_cats:
        return "Mechanistic"
    if safe_hits > 0 or any(p.get("category") == "Safety Warning" for p in papers):
        return "Safety Warning"
    return "Novel (0 renal papers)"


def synthesize_literature_group(lit_group: dict) -> dict:
    """Build deterministic extractive synthesis strictly grounded in retrieved papers."""
    tier = lit_group.get("evidence_tier") or "Unknown"
    eff_hits = int(lit_group.get("efficacy_total_hits") or 0)
    safe_hits = int(lit_group.get("safety_total_hits") or 0)
    provider = lit_group.get("provider") or "unknown"
    papers = lit_group.get("papers") or []

    efficacy_points = [
        {
            "pmid": p.get("pmid"),
            "year": p.get("year") or "—",
            "category": p.get("category") or "Mechanistic",
            "title": p.get("title") or "",
            "finding": p.get("takeaway") or p.get("snippet") or p.get("title") or "",
        }
        for p in papers
        if p.get("query_role") == "efficacy" and p.get("category") != "Safety Warning"
    ][:3]

    safety_points = [
        {
            "pmid": p.get("pmid"),
            "year": p.get("year") or "—",
            "category": p.get("category") or "Safety Warning",
            "title": p.get("title") or "",
            "finding": p.get("takeaway") or p.get("snippet") or p.get("title") or "",
        }
        for p in papers
        if p.get("query_role") == "safety" or p.get("category") == "Safety Warning"
    ][:2]

    if eff_hits == 0 and not efficacy_points:
        novelty_note = "High repurposing novelty: 0 kidney efficacy publications indexed."
    else:
        novelty_note = f"Reported in kidney literature ({eff_hits} efficacy hit(s) indexed)."

    return {
        "verdict": f"{tier} — {eff_hits} kidney efficacy hit(s), {safe_hits} nephrotoxicity/AKI hit(s) via {provider}.",
        "novelty_note": novelty_note,
        "efficacy_points": efficacy_points,
        "safety_points": safety_points,
    }


def search_kidney_literature(
    entity: str,
    disease_context: str = "kidney disease",
    include_safety: bool = True,
    max_papers: int = 6,
) -> dict:
    """Bidirectional kidney efficacy + nephrotoxicity search with 7-day SQLite cache."""
    clean_ent = re.sub(r'["\n\r]+', " ", (entity or "").strip())
    if not clean_ent:
        raise ValueError("entity is required for literature search")
    clean_ctx = (disease_context or "kidney disease").strip()
    n_max = max(2, min(10, int(max_papers)))
    cache_key = "lit2:" + hashlib.sha256(
        f"{clean_ent.lower()}|{clean_ctx.lower()}|{int(include_safety)}|{n_max}".encode()
    ).hexdigest()

    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    renal_expr = _expand_disease_terms(clean_ctx)
    eff_query = f'("{clean_ent}") AND ({renal_expr})'
    eff_n = max(2, n_max - (2 if include_safety else 0))
    eff_res = _run_lit_query(eff_query, max_results=eff_n)

    papers_by_key = {}
    eff_papers = []
    for p in eff_res.get("papers", []):
        cat = _classify_paper(p, is_safety_query=False)
        item = {**p, "category": cat, "query_role": "efficacy"}
        key = p.get("pmid") or p.get("doi") or p.get("title")
        if key and key not in papers_by_key:
            papers_by_key[key] = item
            eff_papers.append(item)

    safe_res = {"total_hits": 0, "papers": [], "provider": eff_res.get("provider")}
    if include_safety and eff_res.get("provider") != "unavailable":
        safe_query = f'("{clean_ent}") AND ({SAFETY_QUERY_TERMS})'
        safe_res = _run_lit_query(safe_query, max_results=2)
        for p in safe_res.get("papers", []):
            cat = _classify_paper(p, is_safety_query=True)
            item = {**p, "category": cat, "query_role": "safety"}
            key = p.get("pmid") or p.get("doi") or p.get("title")
            if key and key not in papers_by_key:
                papers_by_key[key] = item

    merged = list(papers_by_key.values())[:n_max]
    provider = eff_res.get("provider") or "unknown"
    eff_hits = int(eff_res.get("total_hits") or 0)
    safe_hits = int(safe_res.get("total_hits") or 0)
    tier = _overall_evidence_tier(eff_hits, safe_hits, merged, provider)

    out = {
        "entity": clean_ent,
        "disease_context": clean_ctx,
        "provider": provider,
        "fallback_from": eff_res.get("fallback_from"),
        "cached": False,
        "evidence_tier": tier,
        "efficacy_total_hits": eff_hits,
        "safety_total_hits": safe_hits,
        "papers": merged,
    }
    out["synthesis"] = synthesize_literature_group(out)
    if eff_res.get("error"):
        out["error"] = eff_res["error"]
    else:
        _cache_set(cache_key, provider, out)
    return out


def _fetch_trials_once(compound: str, condition: str, n_max: int) -> dict:
    params = urllib.parse.urlencode({
        "query.intr": compound,
        "query.cond": condition,
        "pageSize": str(n_max),
        "countTotal": "true",
    })
    url = f"https://clinicaltrials.gov/api/v2/studies?{params}"
    raw = _http_get(url, timeout=8.0)
    data = json.loads(raw.decode("utf-8", errors="replace"))
    trials = []
    for st in data.get("studies") or []:
        ps = st.get("protocolSection") or {}
        idm = ps.get("identificationModule") or {}
        stm = ps.get("statusModule") or {}
        dsm = ps.get("designModule") or {}
        cnm = ps.get("conditionsModule") or {}
        nct_id = str(idm.get("nctId") or "").strip()
        if not nct_id:
            continue
        phases = dsm.get("phases") or []
        start_s = (stm.get("startDateStruct") or {}).get("date") or ""
        trials.append({
            "nct_id": nct_id,
            "title": _strip_text(idm.get("briefTitle") or idm.get("officialTitle"), 190),
            "phases": phases if phases else ["N/A"],
            "status": str(stm.get("overallStatus") or "UNKNOWN"),
            "conditions": (cnm.get("conditions") or [])[:4],
            "start_date": start_s,
            "url": f"https://clinicaltrials.gov/study/{nct_id}",
        })
    return {"total_count": int(data.get("totalCount") or len(trials)), "trials": trials}


def search_clinical_trials(
    compound: str,
    condition: str = "kidney disease",
    max_trials: int = 5,
) -> dict:
    """Query ClinicalTrials.gov v2 REST API, broadening to 'kidney disease' if narrow yields 0."""
    clean_cp = re.sub(r'["\n\r]+', " ", (compound or "").strip())
    if not clean_cp:
        raise ValueError("compound is required for clinical trials search")
    clean_cond = (condition or "kidney disease").strip()
    n_max = max(1, min(10, int(max_trials)))
    cache_key = "ct2:" + hashlib.sha256(
        f"{clean_cp.lower()}|{clean_cond.lower()}|{n_max}".encode()
    ).hexdigest()

    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        res = _fetch_trials_once(clean_cp, clean_cond, n_max)
    except Exception as exc:
        return {
            "compound": clean_cp,
            "condition": clean_cond,
            "provider": "clinicaltrials.gov",
            "cached": False,
            "total_count": 0,
            "trials": [],
            "error": str(exc)[:160],
        }

    scope_note = None
    eff_cond = clean_cond
    if res["total_count"] == 0 and clean_cond.lower() != "kidney disease":
        try:
            broad = _fetch_trials_once(clean_cp, "kidney disease", n_max)
            scope_note = f"0 trials matched '{clean_cond}'; broadened to 'kidney disease' ({broad['total_count']} found)."
            if broad["total_count"] > 0:
                res = broad
                eff_cond = "kidney disease"
        except Exception:
            pass

    out = {
        "compound": clean_cp,
        "condition": eff_cond,
        "provider": "clinicaltrials.gov",
        "cached": False,
        "total_count": res["total_count"],
        "trials": res["trials"],
    }
    if scope_note:
        out["scope_note"] = scope_note
    _cache_set(cache_key, "clinicaltrials.gov", out)
    return out
