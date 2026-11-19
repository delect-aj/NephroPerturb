"""Low-freedom deterministic SOP router with an optional DeepSeek backend.

The LLM only maps natural language to SOP ids and parameter slots; every score
is computed by the deterministic engine. Without an API key the router falls
back to rule-based parsing (0-LLM mode).
"""
import json
import os
import re

SOP_IDS = ["SOP-1", "SOP-2", "SOP-3", "SOP-4", "SOP-5", "SOP-6"]

SYSTEM_PROMPT = """You are a parameter extractor for NephroPerturb.
Return ONLY compact JSON with keys: sop_id, params, missing, confidence.
sop_id is one of SOP-1..SOP-6:
SOP-1 gene signature reversal; SOP-2 compound profile; SOP-3 pathway/TF query;
SOP-4 target gene mapping; SOP-5 structure/unknown compound; SOP-6 built-in cases.
params must only contain values explicitly present in the user text.
Never invent gene names, drug names or numbers. missing lists required fields.
"""

CASE_NAMES = ["DKD", "LN", "IgAN", "AKI", "CKD", "FSGS"]


def _rule_route(text):
    low = text.lower()
    if re.search(r"sop[- ]?6|案例|队列|case|dkd|ln|igan|aki|ckd|fsgs", low):
        case = next((c for c in CASE_NAMES if c.lower() in low), None)
        return {"sop_id": "SOP-6", "params": {"case_id": case}, "missing": [],
                "confidence": 0.7, "mode": "rules"}
    if re.search(r"smiles|结构|相似|unknown|brd-", low):
        smiles = re.search(r"\b([A-Za-z0-9@+\-\[\]\(\)=#\\/]{12,})\b", text)
        return {"sop_id": "SOP-5",
                "params": {"smiles": smiles.group(1) if smiles else None},
                "missing": [] if smiles else ["smiles"], "confidence": 0.6,
                "mode": "rules"}
    if re.search(r"靶点|target|敲除|敲低|遗传扰动|knockout|crispr|shrna", low):
        gene = re.search(r"\b([A-Z][A-Z0-9]{2,9})\b", text)
        return {"sop_id": "SOP-4", "params": {"gene": gene.group(1) if gene else None},
                "missing": [] if gene else ["gene"], "confidence": 0.6,
                "mode": "rules"}
    if re.search(r"通路|pathway|转录因子|tf|tgf|smad|ppara|nfkb|hif|stat\d", low):
        pairs = re.findall(r"(TGF\w*|SMAD\d|PPAR\w*|NFKB\w*|RELA|HIF\w*|STAT\d)", text, re.I)
        targets = {p: (-1 if re.search(p + r"\s*(抑制|inhibit|-1|下调)", text, re.I) else 1)
                   for p in dict.fromkeys(pairs)}
        return {"sop_id": "SOP-3", "params": {"targets": targets},
                "missing": [] if targets else ["targets"], "confidence": 0.65,
                "mode": "rules"}
    if re.search(r"画像|详情|信息|profile|机制|moa|安全", low):
        return {"sop_id": "SOP-2", "params": {"compound": text.strip()},
                "missing": [], "confidence": 0.55, "mode": "rules"}
    return {"sop_id": "SOP-1", "params": {"free_text": text},
            "missing": ["up_genes", "down_genes"], "confidence": 0.5,
            "mode": "rules"}


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


def summarize(results, question="", use_llm=True):
    top = results.get("results", [])[:5]
    if not top:
        return {"summary": "本次查询没有返回候选。", "llm_used": False}
    lines = [
        f"- {r.get('pert_iname') or r.get('pert_id')}: "
        f"RTPS={r.get('rtps', 0):.2f}, RenalConn={r.get('renalconn', 0):.2f}, "
        f"T-DIKI={r.get('tdiki_tier', 'NA')}, DIRIL={r.get('diril_label', 'NA')}"
        for r in top
    ]
    template = "按 RTPS 排序的前 5 个候选：\n" + "\n".join(lines)
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not use_llm or not api_key:
        return {"summary": template, "llm_used": False}
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
                {"role": "user", "content": question + "\n\n" + json.dumps(top, ensure_ascii=False)},
            ],
        )
        text = response.choices[0].message.content.strip()
        ids = [r.get("pert_id") for r in top]
        mentioned = [i for i in ids if i and i in text]
        verified = bool(mentioned) or len(top) == 0
        if not verified:
            return {"summary": template, "llm_used": True, "fallback": "entity_check_failed"}
        return {"summary": text, "llm_used": True, "verified": True}
    except Exception as exc:
        return {"summary": template, "llm_used": False, "llm_error": str(exc)[:200]}
