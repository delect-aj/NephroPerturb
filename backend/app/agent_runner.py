"""Deterministic SOP executor for /api/v1/agent/run.

Strictly deterministic workflow:
1. Parse intent & parameter slots (0-LLM rules by default; optional DeepSeek).
2. Resolve aliases/names/cohort IDs deterministically.
3. Invoke the pre-wired scoring/lookup tool (zero LLM reasoning).
4. Run NephroSafe annotation pass (T-DIKI v2 + DIRIL counts).
5. Format verified template summary & structured response contract.
"""
import re
import time
from urllib.parse import quote

from .agent import route, summarize as llm_summarize

SOP_TITLES = {
    "SOP-1": "Signature reversal",
    "SOP-2": "Compound kidney profile",
    "SOP-3": "Pathway / TF drug search",
    "SOP-4": "Target & genetic mimicry",
    "SOP-5": "Structure similarity & MoA",
    "SOP-6": "Disease cohort reversal",
    "OUT_OF_SCOPE": "Out of scope",
}

RESULT_TYPES = {
    "SOP-1": "signature",
    "SOP-2": "compound",
    "SOP-3": "pathway",
    "SOP-4": "target",
    "SOP-5": "structure",
    "SOP-6": "case",
}

DEFAULT_CASES = {
    "DKD": "DKD_glom",
    "LN": "LN_glom",
    "IgAN": "ERCB_IgAN_glom",
    "CKD": "CKD",
    "AKI": "AKI",
}

COMPOUND_STOPWORDS = {
    "profile", "show", "kidney", "renal", "compound", "compounds", "drug", "drugs",
    "safety", "safe", "toxicity", "moa", "mechanism", "what", "about", "the", "of",
    "for", "and", "is", "are", "was", "were", "risk", "query", "please", "tell",
    "give", "check", "find", "info", "information", "detail", "details", "its",
    "this", "that", "with", "from", "how", "does", "have", "has", "can", "you",
    "get", "analog", "analogs", "analogue", "analogues", "similar", "similarity",
    "structural", "structurally", "structure", "neighbor", "neighbors", "neighbour",
    "neighbours", "nephroperturb", "mimics", "like",
}

DEFAULT_SUGGESTIONS = [
    "Find reversal drugs for the DKD glomeruli case",
    "Inhibit SMAD3 and TGFb, activate PPARA",
    "Profile dexamethasone",
]


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000.0, 1)


def _fmt_num(val, decimals=1, fallback="—"):
    if val is None or val != val:
        return fallback
    return f"{float(val):.{decimals}f}"


def _fmt_diril(val):
    if val is None or val != val:
        return "—"
    return "Positive" if int(val) == 1 else "Negative"


def _first_moa(moa):
    if not moa:
        return "—"
    return str(moa).split("|")[0].strip() or "—"


def _extract_compound_candidates(text: str):
    brds = re.findall(r"\b(BRD-[A-Z0-9-]+)\b", text, re.I)
    tokens = re.findall(r"\b([A-Za-z][A-Za-z0-9\-]{2,})\b", text)
    filtered = []
    seen = set()
    for tok in brds + sorted(tokens, key=len, reverse=True):
        low = tok.lower()
        if low in COMPOUND_STOPWORDS or low.startswith("nephrotox") or low.startswith("brd-"):
            if not low.startswith("brd-"):
                continue
        key = tok.upper() if low.startswith("brd-") else low
        if key not in seen:
            seen.add(key)
            filtered.append(tok.upper() if low.startswith("brd-") else tok)
    return filtered


def _resolve_compound_token(text: str, hint: str | None, find_fn):
    if hint and len(hint.strip().split()) <= 2:
        hit = find_fn(hint.strip())
        if hit is not None:
            return hit
    for cand in _extract_compound_candidates(text):
        hit = find_fn(cand)
        if hit is not None:
            return hit
    return None


def _resolve_case(text: str, case_hint: str | None, all_cases: list[dict]):
    by_id = {c["case_id"]: c for c in all_cases}
    if case_hint and case_hint in by_id:
        return by_id[case_hint]

    # Longest case_id first so ERCB_DKD_glom wins over DKD / CKD substrings
    for cid in sorted(by_id, key=len, reverse=True):
        if re.search(rf"\b{re.escape(cid)}\b", text, re.I):
            return by_id[cid]

    if not case_hint:
        return None
    disease = case_hint.upper()
    if disease == "IGAN":
        disease = "IgAN"

    if re.search(r"tubul|tubuli|tubulointerstit|小管", text, re.I):
        for c in all_cases:
            if (c.get("disease_code") or "").lower() == disease.lower() and (
                "_tub" in c["case_id"] or "tubul" in (c.get("compartment") or "").lower()
            ):
                return c

    if re.search(r"\bercb\b", text, re.I):
        for c in all_cases:
            if (c.get("disease_code") or "").lower() == disease.lower() and c["case_id"].startswith("ERCB_"):
                return c

    default_id = DEFAULT_CASES.get(disease)
    if default_id and default_id in by_id:
        return by_id[default_id]
    for c in all_cases:
        if (c.get("disease_code") or "").lower() == disease.lower():
            return c
    return None


def _rank_rows_table(rows):
    cols = [
        {"key": "rank", "label": "#"},
        {"key": "compound", "label": "Compound"},
        {"key": "phase", "label": "Phase"},
        {"key": "rtps", "label": "RTPS"},
        {"key": "renalconn", "label": "RenalConn"},
        {"key": "tdiki", "label": "T-DIKI"},
        {"key": "diril", "label": "DIRIL"},
        {"key": "moa", "label": "MoA"},
    ]
    out_rows = []
    for idx, r in enumerate(rows[:15], 1):
        out_rows.append({
            "rank": idx,
            "pert_id": r.get("pert_id"),
            "compound": r.get("pert_iname") or r.get("pert_id") or "—",
            "phase": r.get("clinical_phase") or "—",
            "rtps": _fmt_num(r.get("rtps"), 1),
            "renalconn": _fmt_num(r.get("renalconn"), 1),
            "tdiki": r.get("tdiki_tier") or "NA",
            "diril": _fmt_diril(r.get("diril_label")),
            "moa": _first_moa(r.get("moa")),
        })
    return {"columns": cols, "rows": out_rows}


def _describe_plan(sop_id: str, params: dict) -> str:
    if sop_id == "SOP-1":
        n_up = len(params.get("up_genes") or [])
        n_dn = len(params.get("down_genes") or [])
        flt = params.get("filters") or {}
        tags = [f"up={n_up}", f"down={n_dn}"]
        if flt.get("approved_only"):
            tags.append("approved_only")
        if flt.get("max_diki_tier"):
            tags.append(f"diki<={flt['max_diki_tier']}")
        return f"SOP-1 · {', '.join(tags)}"
    if sop_id == "SOP-2":
        return "SOP-2 · compound lookup"
    if sop_id == "SOP-3":
        t = params.get("targets") or {}
        pairs = ", ".join(f"{k}:{'+' if v > 0 else '-'}{abs(int(v)) if v in (1,-1) else v}" for k, v in t.items())
        return f"SOP-3 · {pairs or 'no targets'}"
    if sop_id == "SOP-4":
        return f"SOP-4 · gene={params.get('gene') or '?'}"
    if sop_id == "SOP-5":
        val = params.get("smiles") or params.get("pert_id") or "lookup by name"
        return f"SOP-5 · {val[:40]}"
    if sop_id == "SOP-6":
        return f"SOP-6 · case_id={params.get('case_id') or '?'}"
    return sop_id


def _base_resp(query, mode, sop_id, status, message, params, resolved, steps, t0,
               facts=None, table=None, summary="", links=None, job_id=None, suggestions=None):
    resp = {
        "query": query,
        "mode": mode,
        "sop_id": sop_id,
        "sop_title": SOP_TITLES.get(sop_id, sop_id),
        "status": status,
        "message": message,
        "params": params,
        "resolved": resolved,
        "steps": steps,
        "result_type": RESULT_TYPES.get(sop_id),
        "facts": facts or [],
        "table": table or {"columns": [], "rows": []},
        "summary": summary or message,
        "links": links or [],
        "job_id": job_id,
        "elapsed_ms": _ms(t0),
    }
    if suggestions:
        resp["suggestions"] = suggestions
    return resp


def run_agent(text: str, use_llm: bool, tools: dict) -> dict:
    """Execute the 5-step deterministic SOP pipeline without LLM reasoning."""
    t_total = time.perf_counter()
    query = (text or "").strip()
    steps = []

    if not query:
        return _base_resp(
            query, "rules", "SOP-1", "needs_input",
            "Please enter a kidney drug-repurposing question or click one of the showcase cards below.",
            {}, {}, steps, t_total,
            suggestions=DEFAULT_SUGGESTIONS,
        )

    # 1. Parse intent
    t0 = time.perf_counter()
    plan = route(query, use_llm=use_llm)
    mode = plan.get("mode", "rules")
    sop_id = plan.get("sop_id", "SOP-1")
    params = dict(plan.get("params") or {})
    router_tool = "deepseek_param_extractor" if mode == "deepseek" else "rule_router"
    plan_detail = _describe_plan(sop_id, params)
    if plan.get("llm_error"):
        plan_detail += f" (DeepSeek fallback to rules: {plan['llm_error'][:60]})"
    steps.append({
        "name": "Parse intent",
        "tool": router_tool,
        "status": "done",
        "detail": plan_detail,
        "ms": _ms(t0),
    })

    if sop_id == "OUT_OF_SCOPE":
        msg = plan.get("message") or (
            "This question is outside NephroPerturb's scope (kidney disease drug repurposing)."
        )
        steps.append({"name": "Resolve parameters", "tool": "guardrail", "status": "skipped",
                      "detail": "Rejected as out-of-scope before database calls", "ms": 0.0})
        return _base_resp(
            query, mode, "OUT_OF_SCOPE", "out_of_scope", msg, params, {}, steps, t_total,
            links=[{"label": "Browse Cohorts", "href": "/cases/"},
                   {"label": "Signature Workbench", "href": "/workbench/"}],
            suggestions=DEFAULT_SUGGESTIONS,
        )

    # 2. Resolve parameters
    t0 = time.perf_counter()
    resolved = {}

    if sop_id == "SOP-6":
        all_cases = (tools["list_cases"]() or {}).get("cases", [])
        case_obj = _resolve_case(query, params.get("case_id"), all_cases)
        if case_obj is None:
            avail = ", ".join(c["case_id"] for c in all_cases)
            msg = (f"No curated GEO cohort matched '{params.get('case_id') or query}'. "
                   f"Available cohorts: {avail}.")
            steps.append({"name": "Resolve parameters", "tool": "case_resolver", "status": "error",
                          "detail": msg, "ms": _ms(t0)})
            return _base_resp(
                query, mode, sop_id, "needs_input", msg, params, {}, steps, t_total,
                links=[{"label": "View All Cohorts", "href": "/cases/"}],
                suggestions=[
                    "Find reversal drugs for the DKD glomeruli case",
                    "Run the LN glomeruli case",
                    "Run the CKD case",
                ],
            )
        resolved = {"case_id": case_obj["case_id"], "disease_code": case_obj.get("disease_code"),
                    "disease_name": case_obj.get("disease_name"), "gse": case_obj.get("gse") or case_obj.get("dataset_accession")}
        steps.append({
            "name": "Resolve parameters", "tool": "case_resolver", "status": "done",
            "detail": f"{case_obj['case_id']} ({case_obj.get('disease_name')}, {resolved['gse']})",
            "ms": _ms(t0),
        })

    elif sop_id == "SOP-2":
        hit = _resolve_compound_token(query, params.get("compound"), tools["find_compound"])
        if hit is None:
            msg = "Could not identify a known compound in your query. Try e.g. 'Profile dexamethasone' or a BRD ID."
            steps.append({"name": "Resolve parameters", "tool": "compound_resolver", "status": "error",
                          "detail": "No compound token matched the 21,299-compound index", "ms": _ms(t0)})
            return _base_resp(
                query, mode, sop_id, "needs_input", msg, params, {}, steps, t_total,
                links=[{"label": "Open Compound Explorer", "href": "/compound/"}],
                suggestions=[
                    "Profile dexamethasone",
                    "Is tacrolimus nephrotoxic? Show its kidney safety profile",
                    "Show the kidney profile of losartan",
                ],
            )
        resolved = {"pert_id": str(hit["pert_id"]), "pert_iname": hit.get("pert_iname") or str(hit["pert_id"])}
        steps.append({
            "name": "Resolve parameters", "tool": "compound_resolver", "status": "done",
            "detail": f"Resolved '{resolved['pert_iname']}' -> {resolved['pert_id']}",
            "ms": _ms(t0),
        })

    elif sop_id == "SOP-5":
        if params.get("smiles"):
            resolved = {"smiles": params["smiles"]}
            steps.append({"name": "Resolve parameters", "tool": "smiles_extractor", "status": "done",
                          "detail": f"SMILES={resolved['smiles']}", "ms": _ms(t0)})
        elif params.get("pert_id"):
            hit = tools["find_compound"](params["pert_id"])
            if hit is not None:
                resolved = {"pert_id": str(hit["pert_id"]), "pert_iname": hit.get("pert_iname")}
            else:
                resolved = {"pert_id": params["pert_id"]}
            steps.append({"name": "Resolve parameters", "tool": "compound_resolver", "status": "done",
                          "detail": f"Reference compound {resolved['pert_id']}", "ms": _ms(t0)})
        else:
            hit = _resolve_compound_token(query, None, tools["find_compound"])
            if hit is None:
                msg = "Please provide a SMILES string, compound name, or BRD ID for structure search."
                steps.append({"name": "Resolve parameters", "tool": "structure_resolver", "status": "error",
                              "detail": "No valid SMILES or known compound name detected", "ms": _ms(t0)})
                return _base_resp(
                    query, mode, sop_id, "needs_input", msg, params, {}, steps, t_total,
                    links=[{"label": "Open Structure Search", "href": "/structure/"}],
                    suggestions=[
                        "Find compounds structurally similar to CC(=O)OC1=CC=CC=C1C(=O)O",
                        "Find analogs of dexamethasone",
                    ],
                )
            resolved = {"pert_id": str(hit["pert_id"]), "pert_iname": hit.get("pert_iname")}
            steps.append({"name": "Resolve parameters", "tool": "compound_resolver", "status": "done",
                          "detail": f"Resolved '{resolved['pert_iname']}' -> {resolved['pert_id']}", "ms": _ms(t0)})

    elif sop_id == "SOP-4":
        gene = params.get("gene")
        if not gene:
            msg = "Please name a human target gene symbol (e.g., 'Which compounds mimic knockdown of TGFBR1?')."
            steps.append({"name": "Resolve parameters", "tool": "gene_resolver", "status": "error",
                          "detail": "No gene symbol found", "ms": _ms(t0)})
            return _base_resp(
                query, mode, sop_id, "needs_input", msg, params, {}, steps, t_total,
                links=[{"label": "Open Target & Genetics", "href": "/target/"}],
                suggestions=["Which compounds mimic knockdown of TGFBR1?", "Target APOL1 knockout mimicry compounds"],
            )
        resolved = {"gene": str(gene).strip()}
        steps.append({"name": "Resolve parameters", "tool": "gene_resolver", "status": "done",
                      "detail": f"Target gene={resolved['gene']}", "ms": _ms(t0)})

    elif sop_id == "SOP-3":
        targets = params.get("targets") or {}
        if not targets:
            msg = "Please specify at least one pathway, TF, or renal module with direction (e.g., 'Inhibit SMAD3 and TGFb, activate PPARA')."
            steps.append({"name": "Resolve parameters", "tool": "pathway_resolver", "status": "error",
                          "detail": "No known pathway/TF matched", "ms": _ms(t0)})
            return _base_resp(
                query, mode, sop_id, "needs_input", msg, params, {}, steps, t_total,
                links=[{"label": "Open Pathway & TF Search", "href": "/pathway-tf/"}],
                suggestions=["Inhibit SMAD3 and TGFb, activate PPARA", "Compounds that inhibit TGFB signaling"],
            )
        resolved = {"targets": targets}
        steps.append({"name": "Resolve parameters", "tool": "pathway_resolver", "status": "done",
                      "detail": ", ".join(f"{k}:{'+1' if v > 0 else '-1'}" for k, v in targets.items()),
                      "ms": _ms(t0)})

    elif sop_id == "SOP-1":
        up_genes = params.get("up_genes") or []
        down_genes = params.get("down_genes") or []
        if not up_genes and not down_genes:
            msg = ("Please provide up-regulated and/or down-regulated gene symbols "
                   "(e.g., 'Up: COL1A1 COL3A1 FN1 TGFB1; Down: NPHS1 NPHS2 PPARA').")
            steps.append({"name": "Resolve parameters", "tool": "signature_parser", "status": "error",
                          "detail": "Both up_genes and down_genes are empty", "ms": _ms(t0)})
            return _base_resp(
                query, mode, sop_id, "needs_input", msg, params, {}, steps, t_total,
                links=[{"label": "Open Signature Workbench", "href": "/workbench/"}],
                suggestions=[
                    "Up: COL1A1 COL3A1 FN1 TGFB1 SERPINE1 LCN2 HAVCR1; Down: NPHS1 NPHS2 PODXL PPARA PPARGC1A CPT1A. Approved drugs only, low nephrotoxicity risk",
                ],
            )
        resolved = {
            "up_genes": up_genes,
            "down_genes": down_genes,
            "context": params.get("context") or "kprl",
            "kidney_compartment": params.get("kidney_compartment"),
            "filters": params.get("filters") or {},
        }
        steps.append({
            "name": "Resolve parameters", "tool": "signature_parser", "status": "done",
            "detail": f"up={len(up_genes)}, down={len(down_genes)}, context={resolved['context']}",
            "ms": _ms(t0),
        })

    # 3. Call deterministic tool
    t0 = time.perf_counter()
    raw_res = None
    try:
        if sop_id == "SOP-1":
            tool_name = "nephro_query_signature"
            endpoint = "POST /api/v1/query/signature"
            raw_res = tools["signature"](
                up_genes=resolved["up_genes"],
                down_genes=resolved["down_genes"],
                context=resolved["context"],
                kidney_compartment=resolved.get("kidney_compartment"),
                filters=resolved.get("filters") or {},
                top_k=20,
            )
            call_detail = f"{endpoint} -> {len(raw_res.get('results', []))} candidates"
        elif sop_id == "SOP-2":
            tool_name = "nephro_profile_compound"
            endpoint = f"GET /api/v1/compound/{resolved['pert_id']}"
            raw_res = tools["compound"](resolved["pert_id"])
            call_detail = f"{endpoint} -> {len(raw_res.get('targets', []))} targets, {len(raw_res.get('top_up_genes', []))} K-PRL up genes"
        elif sop_id == "SOP-3":
            tool_name = "nephro_query_pathway_tf"
            endpoint = "POST /api/v1/query/pathway-tf"
            raw_res = tools["pathway"](targets=resolved["targets"], top_k=20)
            call_detail = f"{endpoint} -> matched {len(raw_res.get('used', []))} features, {len(raw_res.get('results', []))} candidates"
        elif sop_id == "SOP-4":
            tool_name = "nephro_target_mimicry"
            endpoint = f"GET /api/v1/target/{resolved['gene']}"
            raw_res = tools["target"](resolved["gene"])
            call_detail = f"{endpoint} -> {len(raw_res.get('mimicking_compounds', []))} mimicking compounds"
        elif sop_id == "SOP-5":
            tool_name = "nephro_infer_moa"
            endpoint = "POST /api/v1/similarity/structure"
            raw_res = tools["structure"](
                smiles=resolved.get("smiles"),
                pert_id=resolved.get("pert_id"),
                top_k=15,
            )
            call_detail = f"{endpoint} -> {len(raw_res.get('results', []))} structural neighbors"
        elif sop_id == "SOP-6":
            tool_name = "nephro_run_renal_case"
            endpoint = f"GET /api/v1/cases/{resolved['case_id']}"
            raw_res = tools["case"](resolved["case_id"])
            call_detail = f"{endpoint} -> {len(raw_res.get('results', []))} candidates"
        else:
            raise ValueError(f"Unsupported SOP {sop_id}")
        steps.append({"name": "Call deterministic tool", "tool": tool_name, "status": "done",
                      "detail": call_detail, "ms": _ms(t0)})
    except Exception as exc:
        err_msg = getattr(exc, "detail", None) or str(exc)
        tool_map = {
            "SOP-1": "nephro_query_signature", "SOP-2": "nephro_profile_compound",
            "SOP-3": "nephro_query_pathway_tf", "SOP-4": "nephro_target_mimicry",
            "SOP-5": "nephro_infer_moa", "SOP-6": "nephro_run_renal_case",
        }
        steps.append({"name": "Call deterministic tool", "tool": tool_map.get(sop_id, "engine"),
                      "status": "error", "detail": str(err_msg), "ms": _ms(t0)})
        return _base_resp(
            query, mode, sop_id, "error", f"Execution error: {err_msg}", params, resolved, steps, t_total,
            links=[{"label": "Open Workbench", "href": "/workbench/"}],
        )

    # 4. NephroSafe guardrail annotation + 5. Build structured facts, table, summary & links
    t0 = time.perf_counter()
    facts, links = [], []
    table = {"columns": [], "rows": []}
    summary = ""
    job_id = raw_res.get("job_id")

    if sop_id in ("SOP-1", "SOP-6"):
        rows = raw_res.get("results", [])[:15]
        flagged = sum(1 for r in rows if r.get("tdiki_tier") == "High" or r.get("diril_label") == 1)
        steps.append({
            "name": "NephroSafe guardrail", "tool": "nephrosafe_rerank", "status": "done",
            "detail": f"{flagged} of {len(rows)} top candidates flagged (High T-DIKI or DIRIL-positive)",
            "ms": _ms(t0),
        })
        table = _rank_rows_table(rows)
        prov = raw_res.get("provenance") or {}
        top3 = ", ".join(
            f"{r.get('pert_iname') or r.get('pert_id')} (RTPS {_fmt_num(r.get('rtps'), 1)}, T-DIKI {r.get('tdiki_tier') or 'NA'})"
            for r in rows[:3]
        ) or "none"

        if sop_id == "SOP-6":
            case_info = raw_res.get("case") or {}
            facts = [
                {"label": "Cohort ID", "value": resolved["case_id"]},
                {"label": "Disease", "value": case_info.get("disease_name") or resolved.get("disease_code") or "—"},
                {"label": "Accession", "value": f"{case_info.get('gse') or case_info.get('dataset_accession') or '—'} ({case_info.get('platform') or '—'})"},
                {"label": "Sample size", "value": f"n={case_info.get('n_disease', '—')} disease vs {case_info.get('n_control', '—')} control"},
                {"label": "Engine / Context", "value": f"{prov.get('engine', '—')} · {', '.join(prov.get('contexts_used') or []) or 'auto'}"},
                {"label": "NephroSafe Flags", "value": f"{flagged} / {len(rows)} top candidates flagged"},
            ]
            summary = (
                f"Ran cohort {resolved['case_id']} ({case_info.get('disease_name')}, "
                f"{case_info.get('gse') or case_info.get('dataset_accession')}; "
                f"n={case_info.get('n_disease', '?')} vs {case_info.get('n_control', '?')}). "
                f"Top candidates by RTPS: {top3}. {flagged} of the top {len(rows)} carry a nephrotoxicity flag."
            )
            links = [{"label": f"Open {resolved['case_id']} in Disease Cohorts",
                      "href": f"/cases/?run={quote(resolved['case_id'], safe='')}"}]
        else:
            facts = [
                {"label": "Context", "value": resolved["context"]},
                {"label": "Resolved genes", "value": f"Up {prov.get('n_up', len(resolved['up_genes']))} / Down {prov.get('n_down', len(resolved['down_genes']))}"},
                {"label": "Matrix version", "value": prov.get("matrix_version") or "kprl-2026.11"},
                {"label": "NephroSafe Flags", "value": f"{flagged} / {len(rows)} top candidates flagged"},
            ]
            summary = (
                f"Scored {prov.get('n_up', len(resolved['up_genes']))} up / "
                f"{prov.get('n_down', len(resolved['down_genes']))} down genes in {resolved['context']} context. "
                f"Top candidates by RTPS: {top3}. {flagged} of the top {len(rows)} carry a nephrotoxicity flag."
            )
            links = [{"label": "Open in Signature Workbench",
                      "href": f"/workbench/?up={quote(','.join(resolved['up_genes']), safe=',')}&down={quote(','.join(resolved['down_genes']), safe=',')}&context={quote(resolved['context'], safe='')}"}]

        if use_llm and rows:
            s_out = llm_summarize(raw_res, question=query, use_llm=True)
            if s_out.get("llm_used") and s_out.get("verified"):
                summary = s_out["summary"]

    elif sop_id == "SOP-2":
        c = raw_res.get("compound") or {}
        tdiki = raw_res.get("tdiki") or {}
        tier = tdiki.get("tier") or "NA"
        prob = tdiki.get("prob")
        diril_str = _fmt_diril(tdiki.get("diril_label"))
        steps.append({
            "name": "NephroSafe guardrail", "tool": "nephrosafe_profile", "status": "done",
            "detail": f"T-DIKI v2 tier={tier} (p={_fmt_num(prob, 3)}) · DIRIL={diril_str}",
            "ms": _ms(t0),
        })
        name = c.get("pert_iname") or c.get("pert_id") or resolved["pert_id"]
        facts = [
            {"label": "Compound", "value": name},
            {"label": "BRD ID", "value": c.get("pert_id") or "—"},
            {"label": "Clinical Phase", "value": c.get("clinical_phase") or "—"},
            {"label": "MoA", "value": c.get("moa") or "—"},
            {"label": "T-DIKI Risk", "value": f"{tier} (p={_fmt_num(prob, 3)})"},
            {"label": "DIRIL Gold Standard", "value": diril_str},
            {"label": "QED", "value": _fmt_num(c.get("qed"), 3)},
            {"label": "MW", "value": _fmt_num(c.get("mw"), 1)},
        ]
        up_g = raw_res.get("top_up_genes") or []
        dn_g = raw_res.get("top_down_genes") or []
        table = {
            "columns": [
                {"key": "gene", "label": "Gene"},
                {"key": "direction", "label": "Direction"},
                {"key": "z", "label": "K-PRL Z-score"},
            ],
            "rows": (
                [{"gene": g["symbol"], "direction": "Up-regulated", "z": _fmt_num(g.get("z"), 2)} for g in up_g[:10]]
                + [{"gene": g["symbol"], "direction": "Down-regulated", "z": _fmt_num(g.get("z"), 2)} for g in dn_g[:10]]
            ),
        }
        summary = (
            f"{name} ({c.get('pert_id')}, {c.get('clinical_phase') or 'Preclinical/Unknown'}) — "
            f"MoA: {c.get('moa') or 'not annotated'}. "
            f"T-DIKI v2 risk tier is {tier} (p={_fmt_num(prob, 3)}); FDA DIRIL status: {diril_str}. "
            f"Showing top {len(up_g[:10])} up and {len(dn_g[:10])} down K-PRL genes."
        )
        links = [
            {"label": f"Full Compound Card ({name})", "href": f"/compound/?id={quote(c.get('pert_id') or resolved['pert_id'], safe='')}"},
            {"label": "Find Structural Analogs", "href": f"/structure/?q={quote(c.get('pert_id') or resolved['pert_id'], safe='')}"},
        ]

    elif sop_id == "SOP-3":
        rows = raw_res.get("results", [])[:15]
        flagged = sum(1 for r in rows if r.get("tdiki_tier") == "High" or r.get("diril_label") == 1)
        steps.append({
            "name": "NephroSafe guardrail", "tool": "nephrosafe_rerank", "status": "done",
            "detail": f"{flagged} of {len(rows)} top candidates flagged (High T-DIKI or DIRIL-positive)",
            "ms": _ms(t0),
        })
        used = raw_res.get("used") or []
        missing = raw_res.get("missing") or []
        facts = [
            {"label": "Matched features", "value": ", ".join(used) or "—"},
            {"label": "Unrecognized", "value": ", ".join(missing) or "None"},
            {"label": "NephroSafe Flags", "value": f"{flagged} / {len(rows)} top candidates flagged"},
        ]
        table = {
            "columns": [
                {"key": "rank", "label": "#"},
                {"key": "compound", "label": "Compound"},
                {"key": "score", "label": "Pathway/TF Score"},
                {"key": "phase", "label": "Phase"},
                {"key": "tdiki", "label": "T-DIKI"},
            ],
            "rows": [{
                "rank": i,
                "pert_id": r.get("pert_id"),
                "compound": r.get("pert_iname") or r.get("pert_id") or "—",
                "score": _fmt_num(r.get("pathway_tf_score"), 2),
                "phase": r.get("clinical_phase") or "—",
                "tdiki": r.get("tdiki_tier") or "NA",
            } for i, r in enumerate(rows, 1)],
        }
        top3 = ", ".join(
            f"{r.get('pert_iname') or r.get('pert_id')} (score {_fmt_num(r.get('pathway_tf_score'), 2)}, T-DIKI {r.get('tdiki_tier') or 'NA'})"
            for r in rows[:3]
        ) or "none"
        summary = (
            f"Queried precomputed functional activity matrix for {', '.join(used)}. "
            f"Top matching compounds: {top3}. {flagged} of top {len(rows)} carry a nephrotoxicity flag."
        )
        t_param = ",".join(f"{k}:{int(v) if v in (1, -1) else v}" for k, v in resolved["targets"].items())
        links = [{"label": "Open in Pathway & TF Search", "href": f"/pathway-tf/?targets={quote(t_param, safe=':,-')}"}]

    elif sop_id == "SOP-4":
        mimic = raw_res.get("mimicking_compounds", [])[:15]
        drugs = raw_res.get("targeting_drugs") or []
        genetics = raw_res.get("genetic_perturbations") or []
        gene_meta = raw_res.get("gene") or {}
        steps.append({
            "name": "NephroSafe guardrail", "tool": "nephrosafe_annotation", "status": "skipped",
            "detail": "Genetic knockdown mimicry table carries similarity scores only; open individual compounds for T-DIKI",
            "ms": _ms(t0),
        })
        sym = gene_meta.get("symbol") or resolved["gene"]
        facts = [
            {"label": "Gene Symbol", "value": sym},
            {"label": "Entrez ID", "value": str(gene_meta.get("entrez_id") or "—")},
            {"label": "Direct targeting drugs", "value": str(len(drugs))},
            {"label": "LINCS genetic perturbations", "value": str(len(genetics))},
        ]
        table = {
            "columns": [
                {"key": "rank", "label": "#"},
                {"key": "compound", "label": "Knockdown-Mimicking Compound"},
                {"key": "similarity", "label": "Cosine Similarity"},
            ],
            "rows": [{
                "rank": i,
                "pert_id": r.get("pert_id"),
                "compound": r.get("pert_iname") or r.get("pert_id") or "—",
                "similarity": _fmt_num(r.get("similarity"), 3),
            } for i, r in enumerate(mimic, 1)],
        }
        top3 = ", ".join(
            f"{r.get('pert_iname') or r.get('pert_id')} ({_fmt_num(r.get('similarity'), 3)})"
            for r in mimic[:3]
        ) or "none found"
        summary = (
            f"Target {sym} (Entrez {gene_meta.get('entrez_id', '—')}): {len(drugs)} direct targeting drug(s), "
            f"{len(genetics)} LINCS genetic perturbation(s). "
            f"Top knockdown-mimicking compounds: {top3}."
        )
        links = [{"label": f"Open {sym} Target Page", "href": f"/target/?symbol={quote(sym, safe='')}"}]

    elif sop_id == "SOP-5":
        rows = raw_res.get("results", [])[:15]
        steps.append({
            "name": "NephroSafe guardrail", "tool": "nephrosafe_annotation", "status": "skipped",
            "detail": "Structure similarity returns ECFP4 Tanimoto & MoA; click any neighbor for full T-DIKI profile",
            "ms": _ms(t0),
        })
        q_label = resolved.get("smiles") or f"{resolved.get('pert_iname') or ''} ({resolved.get('pert_id')})".strip()
        facts = [
            {"label": "Structure query", "value": q_label},
            {"label": "Fingerprint", "value": "2048-bit Morgan ECFP4 (Tanimoto)"},
            {"label": "Neighbors returned", "value": str(len(rows))},
        ]
        table = {
            "columns": [
                {"key": "rank", "label": "#"},
                {"key": "compound", "label": "Compound"},
                {"key": "tanimoto", "label": "Tanimoto"},
                {"key": "moa", "label": "MoA"},
                {"key": "phase", "label": "Phase"},
            ],
            "rows": [{
                "rank": i,
                "pert_id": r.get("pert_id"),
                "compound": r.get("pert_iname") or r.get("pert_id") or "—",
                "tanimoto": _fmt_num(r.get("tanimoto"), 3),
                "moa": _first_moa(r.get("moa")),
                "phase": r.get("clinical_phase") or "—",
            } for i, r in enumerate(rows, 1)],
        }
        top3 = ", ".join(
            f"{r.get('pert_iname') or r.get('pert_id')} ({_fmt_num(r.get('tanimoto'), 3)}, {_first_moa(r.get('moa'))})"
            for r in rows[:3]
        ) or "none"
        summary = (
            f"Computed ECFP4 Tanimoto similarity against 21,299 compounds for {q_label}. "
            f"Top structural neighbors: {top3}."
        )
        q_param = resolved.get("smiles") or resolved.get("pert_id") or ""
        links = [{"label": "Open in Structure Search", "href": f"/structure/?q={quote(str(q_param), safe='')}"}]

    return _base_resp(
        query, mode, sop_id, "ok", "Completed", params, resolved, steps, t_total,
        facts=facts, table=table, summary=summary, links=links, job_id=job_id,
    )
