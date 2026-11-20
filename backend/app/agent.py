"""Deterministic SOP router (optional DeepSeek backend) with strict grounding.

The LLM only maps natural language to SOP ids and parameter slots; every
score is computed by the deterministic engine (0-LLM mode is fully supported).
Summary generation is guarded by a strict entity+number verifier: any drug id,
drug name or number not present in the supplied result table (within rounding
tolerance) forces an immediate fallback to the deterministic template with
verified=False and a fallback_reason logged.
"""
import json
import os
import re

SOP_IDS = ["SOP-1", "SOP-2", "SOP-3", "SOP-4", "SOP-5", "SOP-6", "OUT_OF_SCOPE"]

SYSTEM_PROMPT = """You are a parameter extractor for NephroPerturb, a kidney drug-repurposing engine.
Return ONLY compact JSON with keys: sop_id, params, missing, confidence.
sop_id is one of SOP-1..SOP-6 or OUT_OF_SCOPE.
SOP-1 gene-signature reversal (params: up_genes, down_genes, context,
kidney_compartment, approved_only, max_diki_tier, collapse_scaffold);
SOP-2 compound profile (compound); SOP-3 pathway/TF query (targets: name->+1/-1);
SOP-4 target gene mapping (gene); SOP-5 structure/unknown compound (smiles or
pert_id); SOP-6 built-in renal cohorts (case_id).
OUT_OF_SCOPE: anything not about kidney disease, drugs, genes, pathways,
structures or this database.
params must only contain values explicitly present in the user text.
Never invent gene names, drug names or numbers. missing lists required fields
that the text does not provide.
"""

CASE_NAMES = ["DKD", "LN", "IgAN", "AKI", "CKD", "FSGS"]
GENE_RE = re.compile(r"\b([A-Z][A-Z0-9][A-Z0-9-]{0,9})\b")
SCOPE_WORDS = re.compile(
    r"肾|kidney|renal|nephr|药|drug|compound|profile|moa|画像|化合物|基因|gene|gwas|"
    r"通路|pathway|靶点|target|smiles|结构|structure|brd-|dkd|ln\b|igan|aki|ckd|fsgs|"
    r"损伤|tox|diki|renin|tgf|smad|ppar|nfkb|hif|stat|糖尿病|diabet|lupus|狼疮|"
    r"上调|下调|signature|up[\s:]|down[\s:]", re.I)
SIGNATURE_HINT = re.compile(r"上调|下调|up[\s:：]|down[\s:：]|signature|基因列表", re.I)

STOP_TOKENS = {"SMILES", "BRD", "SOP", "DKD", "CKD", "AKI", "FSGS", "LN", "IGAN",
               "RTPS", "DIRIL", "LINCS", "PROGENY", "COLLECTRI", "MCP", "API",
               "TOP", "NA", "AND", "OR", "THE", "UP", "DOWN"}


def _gene_tokens(text):
    return [t for t in GENE_RE.findall(text) if t.upper() not in STOP_TOKENS
            and len(t) >= 2]


def _parse_signature(text):
    """Extract up/down gene lists from natural-language SOP-1 requests."""
    up, down = [], []
    up_pat = re.compile(r"(上调|升高|高表达|up-?regulat\w*|up[:\s]|up genes?)[:：]?\s*"
                        r"([A-Za-z0-9,\s、;/_-]+)", re.I)
    down_pat = re.compile(r"(下调|降低|低表达|down-?regulat\w*|down[:\s]|down genes?)[:：]?\s*"
                          r"([A-Za-z0-9,\s、;/_-]+)", re.I)
    for m in up_pat.finditer(text):
        up += _gene_tokens(m.group(2))
    for m in down_pat.finditer(text):
        down += _gene_tokens(m.group(2))
    if not up and not down:
        # "A B C 上调 / D E 下调" word order: tokens before the marker
        before_up = re.split(r"上调|升高|高表达", text)
        if len(before_up) == 2:
            up = _gene_tokens(before_up[0])[-30:]
            down = _gene_tokens(before_up[1])[:30] if "下调" in before_up[1] else []
    up = [g for g in dict.fromkeys(up) if g not in down]
    return up, down


def _parse_filters(text):
    filters = {}
    if re.search(r"已批准|approved|FDA批准|上市", text, re.I):
        filters["approved_only"] = True
    if re.search(r"低肾毒|低风险|low.{0,6}(diki|risk)|安全", text, re.I):
        filters["max_diki_tier"] = "Low"
    if re.search(r"母核|骨架|scaffold|去重", text, re.I):
        filters["collapse_scaffold"] = True
    return filters


def _parse_context(text):
    low = text.lower()
    if "renal_epi" in low or "肾上皮" in text:
        return "renal_epi"
    if "renal_immune" in low or "免疫" in text:
        return "renal_immune"
    if "renal_endo" in low or "内皮" in text:
        return "renal_endo"
    if "pan" in low or "泛细胞" in text:
        return "pan"
    return None


def _parse_compartment(text):
    table = {"podocyte": r"足细胞|podocyte", "pt": r"近端小管|proximal",
             "tubule": r"小管|tubul", "glomerulus": r"小球|glomerul",
             "immune": r"免疫|immune", "endo": r"内皮|endoth"}
    for key, pat in table.items():
        if re.search(pat, text, re.I):
            return key
    return None


def _rule_route(text):
    low = text.lower()
    if not SCOPE_WORDS.search(text):
        return {"sop_id": "OUT_OF_SCOPE", "params": {},
                "missing": [], "confidence": 0.8, "mode": "rules",
                "message": "该问题超出 NephroPerturb 的肾病药物重定位范围。"}
    # explicit up/down gene lists always mean the signature-reversal SOP,
    # even if genes collide with pathway keywords (TGFB1, PPARA ...)
    up_genes, down_genes = _parse_signature(text)
    if SIGNATURE_HINT.search(text) and (up_genes or down_genes):
        params = {"up_genes": up_genes, "down_genes": down_genes}
        ctx = _parse_context(text)
        if ctx:
            params["context"] = ctx
        comp = _parse_compartment(text)
        if comp:
            params["kidney_compartment"] = comp
        params["filters"] = _parse_filters(text)
        missing = [k for k in ("up_genes", "down_genes") if not params.get(k)]
        return {"sop_id": "SOP-1", "params": params, "missing": missing,
                "confidence": 0.8 if not missing else 0.5, "mode": "rules"}
    if re.search(r"sop[- ]?6|案例|队列|case|dkd|ln\b|igan|aki|ckd|fsgs", low):
        case = next((c for c in CASE_NAMES if re.search(rf"\b{c}\b", text, re.I)), None)
        return {"sop_id": "SOP-6", "params": {"case_id": case},
                "missing": [] if case else ["case_id"],
                "confidence": 0.75, "mode": "rules"}
    if re.search(r"smiles|结构|相似|unknown|brd-", low):
        if re.search(r"敲除|敲低|knockout|crispr|shrna|遗传扰动", low):
            gene = re.search(r"\b([A-Z][A-Z0-9]{2,9})\b", text)
            return {"sop_id": "SOP-4",
                    "params": {"gene": gene.group(1) if gene else None},
                    "missing": [] if gene else ["gene"], "confidence": 0.65,
                    "mode": "rules"}
        smiles = re.search(r"\b([A-Za-z0-9@+\-\[\]\(\)=#\\/]{12,})\b", text)
        return {"sop_id": "SOP-5",
                "params": {"smiles": smiles.group(1) if smiles else None},
                "missing": [] if smiles else ["smiles"], "confidence": 0.65,
                "mode": "rules"}
    if re.search(r"靶点|target|敲除|敲低|遗传扰动|knockout|crispr|shrna", low):
        gene = re.search(r"\b([A-Z][A-Z0-9]{2,9})\b", text)
        return {"sop_id": "SOP-4",
                "params": {"gene": gene.group(1) if gene else None},
                "missing": [] if gene else ["gene"], "confidence": 0.65,
                "mode": "rules"}
    if re.search(r"通路|pathway|转录因子|tf\b|tgf|smad|ppara|nfkb|hif|stat\d", low):
        pairs = re.findall(r"(TGF\w*|SMAD\d|PPAR\w*|NFKB\w*|RELA|HIF\w*|STAT\d)",
                           text, re.I)
        targets = {p: (-1 if re.search(p + r"\s*(抑制|inhibit|-1|下调)", text, re.I)
                       else 1) for p in dict.fromkeys(pairs)}
        return {"sop_id": "SOP-3", "params": {"targets": targets},
                "missing": [] if targets else ["targets"], "confidence": 0.7,
                "mode": "rules"}
    if re.search(r"画像|详情|信息|profile|机制|moa|安全|这个药|该药|这个化合物|查一下", low):
        return {"sop_id": "SOP-2", "params": {"compound": text.strip()},
                "missing": [], "confidence": 0.6, "mode": "rules"}
    up, down = _parse_signature(text)
    params = {"up_genes": up, "down_genes": down}
    ctx = _parse_context(text)
    if ctx:
        params["context"] = ctx
    comp = _parse_compartment(text)
    if comp:
        params["kidney_compartment"] = comp
    params["filters"] = _parse_filters(text)
    missing = [k for k in ("up_genes", "down_genes") if not params.get(k)]
    return {"sop_id": "SOP-1", "params": params, "missing": missing,
            "confidence": 0.6 if not missing else 0.45, "mode": "rules"}


def route(text, use_llm=True):
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not use_llm or not api_key:
        return _rule_route(text)
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        response = client.chat.completions.create(
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": text}],
        )
        parsed = json.loads(response.choices[0].message.content)
        if parsed.get("sop_id") not in SOP_IDS:
            raise ValueError("invalid sop_id")
        parsed["mode"] = "deepseek"
        return parsed
    except Exception as exc:  # network/quota/schema failures degrade gracefully
        result = _rule_route(text)
        result["llm_error"] = str(exc)[:200]
        return result


# ---------------------------------------------------------------- verifier
NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_.])(-?\d+(?:\.\d+)?)(%?)")
NAME_RE = re.compile(r"\b([A-Za-z][a-z]+(?:-[a-z]+)+)\b")
BRD_RE = re.compile(r"\bBRD-[A-Z0-9]{4,}\b")
ALLOW_NAMES = {"t-diki", "renalconn", "diril", "lincs", "progeny", "collectri",
               "rtps", "pcr", "dna", "rna", "kg", "mg", "nm", "μm", "um"}
EXEMPT_NUMBERS = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10}


def _numeric_values(obj, out):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.append(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            _numeric_values(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _numeric_values(v, out)


def verify_summary(text, results):
    """Return (ok, reasons) for strict entity+number consistency."""
    rows = results.get("results", [])[:30]
    ids = {str(r.get("pert_id")) for r in rows if r.get("pert_id")}
    names = {str(r.get("pert_iname")).lower() for r in rows if r.get("pert_iname")}
    reasons = []

    bad_ids = [i for i in BRD_RE.findall(text) if i not in ids]
    if bad_ids:
        reasons.append(f"unknown BRD ids: {bad_ids[:5]}")

    bad_names = [n for n in NAME_RE.findall(text)
                 if n.lower() not in names and n.lower() not in ALLOW_NAMES
                 and len(n) > 4]
    if bad_names:
        reasons.append(f"drug names not in results: {bad_names[:5]}")

    values = []
    _numeric_values(rows, values)
    values = np_values = [v for v in values if abs(v) < 1e12]
    for raw, pct in NUMBER_RE.findall(text):
        try:
            val = float(raw)
        except ValueError:
            continue
        if not pct and val == int(val) and (abs(val) <= 10 or 1900 <= val <= 2100):
            continue
        tol = max(0.011, 0.5 * 10 ** (-(len(raw.split(".")[1]) if "." in raw else 0)))
        candidates = [abs(val - v) <= tol for v in np_values]
        if pct:
            candidates += [abs(val / 100.0 - v) <= tol for v in np_values]
        if not any(candidates):
            reasons.append(f"number {raw}{pct} not found in results")
    return (len(reasons) == 0), reasons


def summarize(results, question="", use_llm=True):
    top = results.get("results", [])[:5]
    if not top:
        return {"summary": "本次查询没有返回候选。", "llm_used": False,
                "verified": True}
    lines = [
        f"- {r.get('pert_iname') or r.get('pert_id')}: "
        f"RTPS={r.get('rtps', 0):.2f}, RenalConn={r.get('renalconn', 0):.2f}, "
        f"T-DIKI={r.get('tdiki_tier', 'NA')}, DIRIL={r.get('diril_label', 'NA')}"
        for r in top
    ]
    template = "按 RTPS 排序的前 5 个候选：\n" + "\n".join(lines)
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not use_llm or not api_key:
        return {"summary": template, "llm_used": False, "verified": True}
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        response = client.chat.completions.create(
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
            temperature=0,
            messages=[
                {"role": "system", "content":
                 "Summarize ONLY the supplied result table. Do not add drugs, "
                 "targets or numbers that are absent. Reply in Chinese, 4 sentences max."},
                {"role": "user", "content": question + "\n\n"
                 + json.dumps(top, ensure_ascii=False)},
            ],
        )
        text = response.choices[0].message.content.strip()
        ok, reasons = verify_summary(text, results)
        if not ok:
            return {"summary": template, "llm_used": True, "verified": False,
                    "fallback_reason": "; ".join(reasons)[:300]}
        return {"summary": text, "llm_used": True, "verified": True}
    except Exception as exc:
        return {"summary": template, "llm_used": False, "verified": True,
                "llm_error": str(exc)[:200]}
