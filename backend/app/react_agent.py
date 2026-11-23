"""Unified DeepSeek ReAct + Deterministic Multi-Step Research Agent with SSE streaming."""
from collections import Counter
import json
import os
import re
import threading
import time
from urllib.parse import quote

from .agent_runner import (
    _extract_compound_candidates,
    _first_moa,
    _fmt_diril,
    _fmt_num,
    _rank_rows_table,
    _resolve_case,
    _resolve_compound_token,
)
from .engine.literature import search_clinical_trials, search_kidney_literature
from .model_policy import (
    build_system_prompt,
    canonical_call_key,
    compact_digest,
    get_policy,
)
from .rate_limit import check_llm_quota, record_llm_usage
from .session_store import load_session, resolve_session_references, save_session
from .skills_loader import get_skill, select_skill
from .verifier import (
    EvidencePool,
    NCT_RE,
    PMID_CITE_RE,
    build_repair_prompt,
    verify_grounded_response,
)


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000.0, 1)


# ---------------------------------------------------------------------------
# OpenAI tool schemas (sliced strictly per Skill.allowed_tools)
# ---------------------------------------------------------------------------
TOOL_SCHEMAS = {
    "run_cohort_case": {
        "type": "function",
        "function": {
            "name": "run_cohort_case",
            "description": "Score a curated human kidney biopsy cohort (e.g. DKD_glom, DKD_tub, LN_glom, ERCB_IgAN_glom, AKI, CKD) with optional approved_only / max_diki_tier filters.",
            "parameters": {
                "type": "object",
                "properties": {
                    "case_id": {"type": "string", "description": "Cohort ID or disease name (DKD, LN, IgAN, AKI, CKD)."},
                    "approved_only": {"type": "boolean", "default": False},
                    "max_diki_tier": {"type": "string", "enum": ["Low", "Moderate"]},
                    "top_k": {"type": "integer", "default": 15},
                },
                "required": ["case_id"],
            },
        },
    },
    "score_gene_signature": {
        "type": "function",
        "function": {
            "name": "score_gene_signature",
            "description": "Score compounds reversing an up/down disease gene list against LINCS L1000 / K-PRL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "up_genes": {"type": "array", "items": {"type": "string"}},
                    "down_genes": {"type": "array", "items": {"type": "string"}},
                    "context": {"type": "string", "default": "kprl"},
                    "kidney_compartment": {"type": "string"},
                    "approved_only": {"type": "boolean", "default": False},
                    "max_diki_tier": {"type": "string", "enum": ["Low", "Moderate"]},
                    "top_k": {"type": "integer", "default": 15},
                },
                "required": ["up_genes", "down_genes"],
            },
        },
    },
    "query_pathway_tf": {
        "type": "function",
        "function": {
            "name": "query_pathway_tf",
            "description": "Find compounds matching PROGENy pathway, CollecTRI TF, or renal module directions (-1 inhibit, +1 activate).",
            "parameters": {
                "type": "object",
                "properties": {
                    "targets": {"type": "object", "additionalProperties": {"type": "number"}},
                    "top_k": {"type": "integer", "default": 15},
                },
                "required": ["targets"],
            },
        },
    },
    "profile_compound": {
        "type": "function",
        "function": {
            "name": "profile_compound",
            "description": "Fetch full kidney profile for a compound (MoA, phase, targets, PROGENy, 13 renal modules, K-PRL genes, T-DIKI v2, DIRIL).",
            "parameters": {
                "type": "object",
                "properties": {
                    "token": {"type": "string", "description": "Compound name, BRD-ID, or InChIKey."},
                },
                "required": ["token"],
            },
        },
    },
    "explain_tdiki": {
        "type": "function",
        "function": {
            "name": "explain_tdiki",
            "description": "Explain structural and transcriptomic T-DIKI v2 nephrotoxicity attribution drivers for a compound.",
            "parameters": {
                "type": "object",
                "properties": {
                    "token": {"type": "string"},
                    "top_n": {"type": "integer", "default": 8},
                },
                "required": ["token"],
            },
        },
    },
    "profile_target": {
        "type": "function",
        "function": {
            "name": "profile_target",
            "description": "Get nephron expression, direct drugs, and top knockdown-mimicking compounds for a human gene target.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "top_k": {"type": "integer", "default": 15},
                },
                "required": ["symbol"],
            },
        },
    },
    "find_safe_analogs": {
        "type": "function",
        "function": {
            "name": "find_safe_analogs",
            "description": "Find 2048-bit ECFP4 Tanimoto structural neighbors by SMILES or compound name/BRD-ID, optionally filtered to safer T-DIKI tiers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "smiles": {"type": "string"},
                    "compound": {"type": "string", "description": "Compound name or BRD-ID if no SMILES given."},
                    "max_diki_tier": {"type": "string", "enum": ["Low", "Moderate"]},
                    "top_k": {"type": "integer", "default": 12},
                },
            },
        },
    },
    "compare_compounds": {
        "type": "function",
        "function": {
            "name": "compare_compounds",
            "description": "Head-to-head comparison of 2-4 compounds across T-DIKI/DIRIL safety, clinical phase, MoA, PROGENy pathways, and renal pathology modules.",
            "parameters": {
                "type": "object",
                "properties": {
                    "compounds": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 4},
                },
                "required": ["compounds"],
            },
        },
    },
    "search_literature": {
        "type": "function",
        "function": {
            "name": "search_literature",
            "description": "Search Europe PMC (with PubMed fallback) bidirectionally for kidney efficacy papers and nephrotoxicity warnings; classifies Clinical/Preclinical/Mechanistic/Novel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "Compound name or gene symbol."},
                    "disease_context": {"type": "string", "default": "kidney disease"},
                    "include_safety": {"type": "boolean", "default": True},
                    "max_papers": {"type": "integer", "default": 6},
                },
                "required": ["entity"],
            },
        },
    },
    "search_clinical_trials": {
        "type": "function",
        "function": {
            "name": "search_clinical_trials",
            "description": "Query ClinicalTrials.gov v2 for registered clinical studies of a compound in kidney diseases.",
            "parameters": {
                "type": "object",
                "properties": {
                    "compound": {"type": "string"},
                    "condition": {"type": "string", "default": "kidney disease"},
                    "max_trials": {"type": "integer", "default": 5},
                },
                "required": ["compound"],
            },
        },
    },
}


# ---------------------------------------------------------------------------
# Tool Executor returning (digest_for_llm, ui_payload, summary_str)
# ---------------------------------------------------------------------------
def _compact_candidates_list(rows: list[dict]) -> list[dict]:
    out = []
    for idx, r in enumerate(rows[:15], 1):
        out.append({
            "rank": idx,
            "pert_id": r.get("pert_id"),
            "pert_iname": r.get("pert_iname") or r.get("pert_id"),
            "clinical_phase": r.get("clinical_phase") or "—",
            "rtps": round(float(r["rtps"]), 2) if r.get("rtps") is not None else None,
            "renalconn": round(float(r["renalconn"]), 2) if r.get("renalconn") is not None else None,
            "pathway_tf_score": round(float(r["pathway_tf_score"]), 2) if r.get("pathway_tf_score") is not None else None,
            "tanimoto": round(float(r["tanimoto"]), 3) if r.get("tanimoto") is not None else None,
            "similarity": round(float(r["similarity"]), 3) if r.get("similarity") is not None else None,
            "tdiki_tier": r.get("tdiki_tier") or "NA",
            "tdiki_prob": round(float(r["tdiki_prob"]), 3) if r.get("tdiki_prob") is not None else None,
            "diril_label": int(r["diril_label"]) if r.get("diril_label") is not None else None,
            "moa": _first_moa(r.get("moa")),
        })
    return out


def _execute_tool(
    name: str,
    args: dict,
    tools: dict,
    session_state: dict,
    pool: EvidencePool,
    include_literature: bool,
) -> tuple[dict, dict, str]:
    """Execute one deterministic tool and ingest both raw and rounded digest values."""
    digest, ui, summary = _dispatch_tool(
        name, args, tools, session_state, pool, include_literature
    )
    pool.ingest(digest)
    return digest, ui, summary


def _dispatch_tool(
    name: str,
    args: dict,
    tools: dict,
    session_state: dict,
    pool: EvidencePool,
    include_literature: bool,
) -> tuple[dict, dict, str]:
    """Dispatch one deterministic tool and update evidence pool + session ledger."""
    if name in ("search_literature", "search_clinical_trials") and not include_literature:
        msg = "Literature & clinical trial tools are disabled for this run."
        return {"error": msg}, {}, msg

    if name == "run_cohort_case":
        all_cases = (tools["list_cases"]() or {}).get("cases", [])
        case_hint = str(args.get("case_id") or "").strip()
        case_obj = _resolve_case(case_hint, case_hint, all_cases)
        if case_obj is None:
            avail = ", ".join(c["case_id"] for c in all_cases[:10])
            raise ValueError(f"Unknown cohort '{case_hint}'. Available: {avail}")
        cid = case_obj["case_id"]
        filters = {}
        if args.get("approved_only"):
            filters["approved_only"] = True
        if args.get("max_diki_tier"):
            filters["max_diki_tier"] = str(args["max_diki_tier"])
        top_k = max(5, min(25, int(args.get("top_k") or 15)))
        if filters and "case_filtered" in tools:
            raw = tools["case_filtered"](cid, filters=filters, top_k=top_k)
        else:
            raw = tools["case"](cid)
        rows = (raw.get("results") or [])[:top_k]
        pool.ingest(raw)
        cinfo = raw.get("case") or case_obj
        session_state["active_case_id"] = cid
        session_state["active_disease"] = cinfo.get("disease_name") or cinfo.get("disease_code") or cid
        session_state["candidates"] = _compact_candidates_list(rows)
        flagged = sum(1 for r in rows[:5] if r.get("tdiki_tier") == "High" or r.get("diril_label") == 1)
        table = _rank_rows_table(rows)
        facts = [
            {"label": "Cohort ID", "value": cid},
            {"label": "Disease", "value": session_state["active_disease"]},
            {"label": "GEO Accession", "value": cinfo.get("gse") or cinfo.get("dataset_accession") or "—"},
            {"label": "Top-5 Toxic Flags", "value": f"{flagged} / {min(5, len(rows))} flagged"},
        ]
        if filters:
            facts.append({"label": "Active Filters", "value": ", ".join(f"{k}={v}" for k, v in filters.items())})
        digest = {
            "case_id": cid,
            "disease": session_state["active_disease"],
            "gse": cinfo.get("gse") or cinfo.get("dataset_accession"),
            "filters": filters,
            "top5_toxic_flagged": flagged,
            "results": _compact_candidates_list(rows[:6]),
        }
        ui = {
            "table": table,
            "facts": facts,
            "links": [{"label": f"Open {cid} Cohort", "href": f"/cases/?run={quote(cid, safe='')}"}],
            "raw_rows": rows,
            "disease_context": session_state["active_disease"],
        }
        return digest, ui, f"{cid} -> {len(rows)} candidates ({flagged}/5 top toxic)"

    if name == "score_gene_signature":
        up = [str(g).strip().upper() for g in (args.get("up_genes") or []) if str(g).strip()]
        dn = [str(g).strip().upper() for g in (args.get("down_genes") or []) if str(g).strip()]
        filters = {}
        if args.get("approved_only"):
            filters["approved_only"] = True
        if args.get("max_diki_tier"):
            filters["max_diki_tier"] = str(args["max_diki_tier"])
        top_k = max(5, min(25, int(args.get("top_k") or 15)))
        raw = tools["signature"](
            up_genes=up,
            down_genes=dn,
            context=args.get("context") or "kprl",
            kidney_compartment=args.get("kidney_compartment"),
            filters=filters,
            top_k=top_k,
        )
        rows = (raw.get("results") or [])[:top_k]
        pool.ingest(raw)
        session_state["candidates"] = _compact_candidates_list(rows)
        if not session_state.get("active_disease"):
            session_state["active_disease"] = "kidney disease"
        flagged = sum(1 for r in rows[:5] if r.get("tdiki_tier") == "High" or r.get("diril_label") == 1)
        prov = raw.get("provenance") or {}
        facts = [
            {"label": "Context", "value": prov.get("context") or "kprl"},
            {"label": "Resolved Genes", "value": f"Up {prov.get('n_up', len(up))} / Down {prov.get('n_down', len(dn))}"},
            {"label": "Top-5 Toxic Flags", "value": f"{flagged} / {min(5, len(rows))} flagged"},
        ]
        if filters:
            facts.append({"label": "Active Filters", "value": ", ".join(f"{k}={v}" for k, v in filters.items())})
        digest = {
            "n_up": prov.get("n_up", len(up)),
            "n_down": prov.get("n_down", len(dn)),
            "context": prov.get("context"),
            "filters": filters,
            "top5_toxic_flagged": flagged,
            "results": _compact_candidates_list(rows[:8]),
        }
        ui = {
            "table": _rank_rows_table(rows),
            "facts": facts,
            "links": [{"label": "Open in Workbench", "href": f"/workbench/?up={quote(','.join(up), safe=',')}&down={quote(','.join(dn), safe=',')}"}],
            "raw_rows": rows,
            "disease_context": session_state.get("active_disease") or "kidney fibrosis",
        }
        return digest, ui, f"Signature screen -> {len(rows)} candidates ({flagged}/5 top toxic)"

    if name == "query_pathway_tf":
        targets = args.get("targets") or {}
        top_k = max(5, min(25, int(args.get("top_k") or 15)))
        raw = tools["pathway"](targets=targets, top_k=top_k)
        rows = (raw.get("results") or [])[:top_k]
        pool.ingest(raw)
        session_state["candidates"] = _compact_candidates_list(rows)
        flagged = sum(1 for r in rows[:5] if r.get("tdiki_tier") == "High" or r.get("diril_label") == 1)
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
        used = raw.get("used") or []
        facts = [
            {"label": "Matched Features", "value": ", ".join(used) or "—"},
            {"label": "Top-5 Toxic Flags", "value": f"{flagged} / {min(5, len(rows))} flagged"},
        ]
        digest = {"used": used, "missing": raw.get("missing") or [], "top5_toxic_flagged": flagged, "results": _compact_candidates_list(rows[:8])}
        t_param = ",".join(f"{k}:{int(v) if v in (1, -1) else v}" for k, v in targets.items())
        ui = {
            "table": table,
            "facts": facts,
            "links": [{"label": "Open in Pathway Search", "href": f"/pathway-tf/?targets={quote(t_param, safe=':,-')}"}],
            "raw_rows": rows,
            "disease_context": "renal fibrosis",
        }
        return digest, ui, f"Pathway/TF screen -> {len(rows)} candidates ({len(used)} features)"

    if name == "profile_compound":
        tok = str(args.get("token") or "").strip()
        hit = _resolve_compound_token(tok, tok, tools["find_compound"])
        pid_or_tok = str(hit["pert_id"]) if hit is not None else tok
        raw = tools["compound"](pid_or_tok, top_genes=10)
        pool.ingest(raw)
        c = raw.get("compound") or {}
        tdiki = raw.get("tdiki") or {}
        cname = c.get("pert_iname") or c.get("pert_id") or tok
        pid = str(c.get("pert_id") or pid_or_tok)
        func = raw.get("functional_activity") or {}
        top_mods = dict(list((func.get("renal_modules") or {}).items())[:5])
        top_pw = {k: v for k, v in sorted((func.get("progeny") or {}).items(), key=lambda x: -abs(float(x[1])))[:5]}
        session_state.setdefault("compounds_detail", {})[cname.lower()] = {
            "pert_id": pid, "pert_iname": cname, "tdiki_tier": tdiki.get("tier"), "diril_label": tdiki.get("diril_label"),
        }
        if not session_state.get("candidates"):
            session_state["candidates"] = [{
                "rank": 1, "pert_id": pid, "pert_iname": cname,
                "clinical_phase": c.get("clinical_phase"), "tdiki_tier": tdiki.get("tier"),
                "tdiki_prob": tdiki.get("prob"), "diril_label": tdiki.get("diril_label"),
                "moa": c.get("moa"),
            }]
        up_g = raw.get("top_up_genes") or []
        dn_g = raw.get("top_down_genes") or []
        facts = [
            {"label": "Compound", "value": f"{cname} ({pid})"},
            {"label": "Clinical Phase", "value": c.get("clinical_phase") or "Preclinical"},
            {"label": "MoA", "value": c.get("moa") or "—"},
            {"label": "NephroSafe T-DIKI", "value": f"{tdiki.get('tier', 'NA')} (p={_fmt_num(tdiki.get('prob'), 3)})"},
            {"label": "DIRIL Gold Standard", "value": _fmt_diril(tdiki.get("diril_label"))},
            {"label": "Known Targets", "value": ", ".join(t.get("target_symbol", "") for t in (raw.get("targets") or [])[:5]) or "—"},
        ]
        table = {
            "columns": [
                {"key": "gene", "label": "K-PRL Gene"},
                {"key": "direction", "label": "Direction"},
                {"key": "z", "label": "Z-score"},
            ],
            "rows": (
                [{"gene": g["symbol"], "direction": "Up-regulated", "z": _fmt_num(g.get("z"), 2)} for g in up_g[:8]]
                + [{"gene": g["symbol"], "direction": "Down-regulated", "z": _fmt_num(g.get("z"), 2)} for g in dn_g[:8]]
            ),
        }
        digest = {
            "pert_id": pid,
            "pert_iname": cname,
            "clinical_phase": c.get("clinical_phase"),
            "moa": c.get("moa"),
            "tdiki_tier": tdiki.get("tier"),
            "tdiki_prob": round(float(tdiki["prob"]), 3) if tdiki.get("prob") is not None else None,
            "diril_label": tdiki.get("diril_label"),
            "targets": [t.get("target_symbol") for t in (raw.get("targets") or [])[:6]],
            "top_progeny": top_pw,
            "top_renal_modules": top_mods,
            "top_up_genes": up_g[:5],
            "top_down_genes": dn_g[:5],
        }
        ui = {
            "facts": facts,
            "kprl_table": table,
            "links": [{"label": f"Compound Card ({cname})", "href": f"/compound/?id={quote(pid, safe='')}"}],
        }
        return digest, ui, f"{cname} · T-DIKI={tdiki.get('tier', 'NA')} (p={_fmt_num(tdiki.get('prob'), 3)}), DIRIL={_fmt_diril(tdiki.get('diril_label'))}"

    if name == "explain_tdiki":
        tok = str(args.get("token") or "").strip()
        hit = _resolve_compound_token(tok, tok, tools["find_compound"])
        pid_or_tok = str(hit["pert_id"]) if hit is not None else tok
        raw = tools["explain"](pid_or_tok, top_n=int(args.get("top_n") or 8))
        raw_contribs = (
            raw.get("contributions")
            or raw.get("top_contributors")
            or raw.get("contributors")
            or raw.get("features")
            or []
        )
        contribs = [
            {
                "feature": c.get("feature"),
                "contribution": round(float(c["contribution"]), 3) if c.get("contribution") is not None else None,
                "value": round(float(c["value"]), 3) if c.get("value") is not None else None,
            }
            for c in raw_contribs[:6]
        ]
        digest = {
            "pert_id": raw.get("pert_id"),
            "tdiki_tier": raw.get("tdiki_tier"),
            "tdiki_prob": round(float(raw["tdiki_prob"]), 3) if raw.get("tdiki_prob") is not None else None,
            "tdiki_struct": round(float(raw["tdiki_struct"]), 3) if raw.get("tdiki_struct") is not None else None,
            "tdiki_tx": round(float(raw["tdiki_tx"]), 3) if raw.get("tdiki_tx") is not None else None,
            "top_contributions": contribs,
        }
        pool.ingest(raw)
        pool.ingest(digest)
        return digest, {}, f"T-DIKI attribution for {raw.get('pert_id') or tok}: tier={raw.get('tdiki_tier', 'NA')} ({len(contribs)} drivers)"

    if name == "profile_target":
        sym = str(args.get("symbol") or "").strip().upper()
        top_k = max(5, min(25, int(args.get("top_k") or 15)))
        raw = tools["target"](sym, top_k=top_k)
        pool.ingest(raw)
        mimic = (raw.get("mimicking_compounds") or [])[:top_k]
        drugs = raw.get("targeting_drugs") or []
        gene_meta = raw.get("gene") or {}
        if mimic:
            session_state["candidates"] = _compact_candidates_list(mimic)
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
        facts = [
            {"label": "Target Gene", "value": f"{gene_meta.get('symbol') or sym} (Entrez {gene_meta.get('entrez_id') or '—'})"},
            {"label": "Direct Drugs", "value": str(len(drugs))},
            {"label": "Knockdown Mimics", "value": str(len(mimic))},
            {"label": "Top Direct Drug", "value": (drugs[0].get("pert_iname") or drugs[0].get("pert_id")) if drugs else "None indexed"},
        ]
        digest = {
            "gene": gene_meta.get("symbol") or sym,
            "entrez_id": gene_meta.get("entrez_id"),
            "kidney_expression": raw.get("kidney_expression") or {},
            "direct_targeting_drugs": drugs[:6],
            "mimicking_compounds": mimic[:8],
        }
        ui = {
            "table": table,
            "facts": facts,
            "links": [{"label": f"Open {sym} Target Page", "href": f"/target/?symbol={quote(sym, safe='')}"}],
            "raw_rows": mimic,
        }
        return digest, ui, f"{sym} -> {len(drugs)} direct drugs, {len(mimic)} knockdown mimics"

    if name == "find_safe_analogs":
        smiles = args.get("smiles")
        compound = args.get("compound")
        max_tier = args.get("max_diki_tier")
        top_k = max(5, min(20, int(args.get("top_k") or 12)))
        pid = None
        src_name_low = None
        q_label = smiles or compound or ""
        if not smiles and compound:
            hit = _resolve_compound_token(compound, compound, tools["find_compound"])
            if hit is None:
                raise LookupError(f"Compound '{compound}' not found")
            pid = str(hit["pert_id"])
            src_name_low = str(hit.get("pert_iname") or "").strip().lower() or None
            q_label = f"{hit.get('pert_iname') or pid} ({pid})"
        scan_k = 120 if max_tier else max(25, top_k * 2)
        raw = tools["structure"](smiles=smiles, pert_id=pid, top_k=scan_k)
        all_hits = raw.get("results") or []

        def _distinct(items: list[dict]) -> list[dict]:
            seen_names = set()
            out = []
            for r in items:
                if pid and r.get("pert_id") == pid:
                    continue
                nm = str(r.get("pert_iname") or "").strip().lower()
                if src_name_low and nm == src_name_low:
                    continue
                key = nm or str(r.get("pert_id"))
                if key in seen_names:
                    continue
                seen_names.add(key)
                out.append(r)
            return out

        distinct_hits = _distinct(all_hits)
        if max_tier == "Low":
            filtered = [r for r in distinct_hits if r.get("tdiki_tier") == "Low" and r.get("diril_label") != 1]
        elif max_tier == "Moderate":
            filtered = [r for r in distinct_hits if r.get("tdiki_tier") in ("Low", "Moderate") and r.get("diril_label") != 1]
        else:
            filtered = distinct_hits
        safe_count = len(filtered)
        rows = (filtered if filtered else distinct_hits)[:top_k]
        pool.ingest({"results": rows})
        session_state["candidates"] = _compact_candidates_list(rows)
        moas = [m for r in rows[:8] for m in str(r.get("moa") or "").split("|") if m.strip()]
        consensus_moa = Counter(moas).most_common(1)[0][0] if moas else "—"
        table = {
            "columns": [
                {"key": "rank", "label": "#"},
                {"key": "compound", "label": "Structural Analog"},
                {"key": "tanimoto", "label": "Tanimoto"},
                {"key": "tdiki", "label": "T-DIKI"},
                {"key": "diril", "label": "DIRIL"},
                {"key": "moa", "label": "MoA"},
                {"key": "phase", "label": "Phase"},
            ],
            "rows": [{
                "rank": i,
                "pert_id": r.get("pert_id"),
                "compound": r.get("pert_iname") or r.get("pert_id") or "—",
                "tanimoto": _fmt_num(r.get("tanimoto"), 3),
                "tdiki": r.get("tdiki_tier") or "NA",
                "diril": _fmt_diril(r.get("diril_label")),
                "moa": _first_moa(r.get("moa")),
                "phase": r.get("clinical_phase") or "—",
            } for i, r in enumerate(rows, 1)],
        }
        filter_note = (
            f"T-DIKI <= {max_tier} ({safe_count} found in top {scan_k})"
            if max_tier
            else "None (all distinct neighbors)"
        )
        facts = [
            {"label": "Structure Query", "value": q_label[:48]},
            {"label": "Consensus MoA", "value": consensus_moa},
            {"label": "Safety Filter", "value": filter_note},
            {"label": "Neighbors Returned", "value": str(len(rows))},
        ]
        digest = {
            "query": q_label,
            "consensus_moa": consensus_moa,
            "max_diki_tier": max_tier,
            "safe_analogs_found": safe_count,
            "scanned_top_k": scan_k,
            "results": _compact_candidates_list(rows[:6]),
        }
        pool.ingest(digest)
        q_param = smiles or pid or ""
        ui = {
            "table": table,
            "facts": facts,
            "links": [{"label": "Open Structure Search", "href": f"/structure/?q={quote(str(q_param), safe='')}"}],
            "raw_rows": rows,
        }
        return digest, ui, f"{len(rows)} distinct ECFP4 neighbors (safe={safe_count}/{scan_k}, consensus MoA: {consensus_moa})"

    if name == "compare_compounds":
        tokens = [str(x).strip() for x in (args.get("compounds") or []) if str(x).strip()]
        comp_res = tools["compare"](tokens)
        pool.ingest(comp_res)
        items = comp_res.get("compounds") or []
        session_state["candidates"] = _compact_candidates_list(items)
        digest = comp_res
        ui = {"comparison": comp_res}
        names = " vs ".join(c["pert_iname"] for c in items)
        return digest, ui, f"Compared {names} across pathways, renal modules & NephroSafe risk"

    if name == "search_literature":
        entity = str(args.get("entity") or "").strip()
        dctx = str(args.get("disease_context") or session_state.get("active_disease") or "kidney disease").strip()
        inc_safe = bool(args.get("include_safety", True))
        max_p = max(2, min(8, int(args.get("max_papers") or 6)))
        lit = search_kidney_literature(entity, disease_context=dctx, include_safety=inc_safe, max_papers=max_p)
        pool.ingest(lit)
        pmids = [p["pmid"] for p in (lit.get("papers") or []) if p.get("pmid")]
        session_state.setdefault("pmids", []).extend(pmids)
        lit_map = session_state.setdefault("literature_by_entity", {})
        prev = lit_map.get(entity.lower()) or {"pmids": [], "ncts": []}
        lit_map[entity.lower()] = {
            "entity": entity,
            "evidence_tier": lit.get("evidence_tier"),
            "pmids": list(dict.fromkeys((prev.get("pmids") or []) + pmids)),
            "ncts": prev.get("ncts") or [],
        }
        compact_papers = [
            {
                "pmid": p.get("pmid"),
                "role": p.get("query_role"),
                "cat": p.get("category"),
                "year": p.get("year"),
                "journal": p.get("journal"),
                "title": (p.get("title") or "")[:110],
                "takeaway": (p.get("takeaway") or p.get("snippet") or "")[:230],
            }
            for p in (lit.get("papers") or [])[:5]
        ]
        synth = lit.get("synthesis") or {}
        digest = {
            "entity": lit.get("entity"),
            "provider": lit.get("provider"),
            "evidence_tier": lit.get("evidence_tier"),
            "efficacy_hits": lit.get("efficacy_total_hits"),
            "safety_hits": lit.get("safety_total_hits"),
            "novelty": synth.get("novelty_note"),
            "papers": compact_papers,
        }
        pool.ingest(digest)
        if lit.get("error"):
            digest["error"] = lit["error"]
        ui = {"literature": lit}
        cache_tag = " [cached]" if lit.get("cached") else ""
        return (
            digest,
            ui,
            f"{entity}: tier={lit.get('evidence_tier')} ({len(lit.get('papers', []))} papers via {lit.get('provider')}{cache_tag})",
        )

    if name == "search_clinical_trials":
        comp = str(args.get("compound") or "").strip()
        cond = str(args.get("condition") or session_state.get("active_disease") or "kidney disease").strip()
        max_t = max(1, min(8, int(args.get("max_trials") or 5)))
        ct = search_clinical_trials(comp, condition=cond, max_trials=max_t)
        pool.ingest(ct)
        ncts = [t["nct_id"] for t in (ct.get("trials") or []) if t.get("nct_id")]
        session_state.setdefault("ncts", []).extend(ncts)
        lit_map = session_state.setdefault("literature_by_entity", {})
        prev = lit_map.get(comp.lower()) or {"entity": comp, "evidence_tier": "Unknown", "pmids": [], "ncts": []}
        prev["ncts"] = list(dict.fromkeys((prev.get("ncts") or []) + ncts))
        lit_map[comp.lower()] = prev
        digest = {
            "compound": ct.get("compound"),
            "condition": ct.get("condition"),
            "total_count": ct.get("total_count"),
            "trials": (ct.get("trials") or [])[:4],
        }
        if ct.get("scope_note"):
            digest["scope_note"] = ct["scope_note"]
        if ct.get("error"):
            digest["error"] = ct["error"]
        ui = {"clinical_trials": ct}
        return digest, ui, f"{comp}: {ct.get('total_count', 0)} ClinicalTrials.gov kidney studies"


# ---------------------------------------------------------------------------
# Deterministic Synthesis & Context-Aware Suggestions
# ---------------------------------------------------------------------------
def _first_safe_candidates(rows: list[dict], limit: int = 2) -> list[tuple[str, str]]:
    """Return unique (pert_id, pert_iname) pairs prioritizing NephroSafe Low/Moderate hits."""
    safe: list[tuple[str, str]] = []
    seen = set()
    for r in rows:
        if r.get("tdiki_tier") in ("Low", "Moderate") and r.get("diril_label") != 1:
            pid = str(r.get("pert_id") or "").strip()
            nm = str(r.get("pert_iname") or pid).strip()
            if pid and nm.lower() not in seen:
                seen.add(nm.lower())
                safe.append((pid, nm))
                if len(safe) >= limit:
                    return safe
    for r in rows:
        pid = str(r.get("pert_id") or "").strip()
        nm = str(r.get("pert_iname") or pid).strip()
        if pid and nm.lower() not in seen:
            seen.add(nm.lower())
            safe.append((pid, nm))
            if len(safe) >= limit:
                break
    return safe


def _build_references(summary: str, artifacts: dict) -> list[dict]:
    """Deterministically build a verified numbered bibliography from cited & retrieved sources."""
    papers_by_pmid: dict[str, dict] = {}
    ordered_papers: list[dict] = []
    for grp in artifacts.get("literature") or []:
        ent = grp.get("entity") or ""
        for p in grp.get("papers") or []:
            pm = str(p.get("pmid") or "").strip()
            if pm and pm not in papers_by_pmid:
                rec = {
                    "kind": "paper",
                    "id": f"PMID:{pm}",
                    "pmid": pm,
                    "authors": p.get("authors") or "et al.",
                    "year": p.get("year") or "—",
                    "title": p.get("title") or "",
                    "journal": p.get("journal") or "",
                    "category": p.get("category") or "Literature",
                    "entity": ent,
                    "url": p.get("url") or f"https://pubmed.ncbi.nlm.nih.gov/{pm}/",
                }
                papers_by_pmid[pm] = rec
                ordered_papers.append(rec)

    trials_by_nct: dict[str, dict] = {}
    ordered_trials: list[dict] = []
    for grp in artifacts.get("clinical_trials") or []:
        cp = grp.get("compound") or ""
        for tr in grp.get("trials") or []:
            nct = str(tr.get("nct_id") or "").strip().upper()
            if nct and nct not in trials_by_nct:
                rec = {
                    "kind": "trial",
                    "id": nct,
                    "nct_id": nct,
                    "title": tr.get("title") or "",
                    "phases": tr.get("phases") or ["N/A"],
                    "status": tr.get("status") or "UNKNOWN",
                    "compound": cp,
                    "url": tr.get("url") or f"https://clinicaltrials.gov/study/{nct}",
                }
                trials_by_nct[nct] = rec
                ordered_trials.append(rec)

    refs: list[dict] = []
    seen: set[str] = set()

    # 1) Cited PMIDs and NCTs in order of appearance in summary
    for m in re.finditer(
        r"(?:PMID[:\s#-]*(\d{5,9}))|\b(NCT\d{8})\b",
        summary or "",
        re.I,
    ):
        pm = m.group(1)
        nct = m.group(2).upper() if m.group(2) else None
        if pm and pm in papers_by_pmid and f"PMID:{pm}" not in seen:
            seen.add(f"PMID:{pm}")
            refs.append({**papers_by_pmid[pm], "cited_in_text": True})
        elif nct and nct in trials_by_nct and nct not in seen:
            seen.add(nct)
            refs.append({**trials_by_nct[nct], "cited_in_text": True})

    # 2) If summary didn't cite every key source or cited none, append top supporting sources
    if len(refs) < 4:
        for rec in ordered_papers[:4] + ordered_trials[:2]:
            if rec["id"] not in seen:
                seen.add(rec["id"])
                refs.append({**rec, "cited_in_text": False})
                if len(refs) >= 8:
                    break

    for idx, r in enumerate(refs, 1):
        r["index"] = idx
    return refs


def _append_literature_section(lines: list[str], lits: list[dict], trials: list[dict], heading: str) -> None:
    lines.append(f"\n{heading}")
    if not lits and not trials:
        lines.append("No kidney literature or clinical trial records were retrieved for this turn.")
        return
    trials_by_name = {str(t.get("compound", "")).lower(): t for t in trials}
    seen_trial_ents = set()
    eff_paragraphs: list[str] = []
    safe_paragraphs: list[str] = []

    for lit in lits:
        ent = str(lit.get("entity") or "Unknown")
        seen_trial_ents.add(ent.lower())
        synth = lit.get("synthesis") or {}
        tier = lit.get("evidence_tier") or "Unknown"
        eff_hits = int(lit.get("efficacy_total_hits") or 0)
        safe_hits = int(lit.get("safety_total_hits") or 0)
        eff_pts = synth.get("efficacy_points") or []
        safe_pts = synth.get("safety_points") or []

        if eff_pts:
            findings_txt = " ".join(
                f"{pt.get('finding').rstrip('.')} [PMID:{pt['pmid']}]."
                if pt.get("pmid")
                else f"{pt.get('finding').rstrip('.')}."
                for pt in eff_pts[:2]
            )
            eff_paragraphs.append(
                f"For **{ent}** (`{tier}` evidence; {eff_hits} kidney efficacy hits via {lit.get('provider')}), "
                f"prior studies report: {findings_txt}"
            )
        else:
            eff_paragraphs.append(
                f"**{ent}** has 0 indexed kidney efficacy publications (`Novel (0 renal papers)`), "
                f"positioning it as an untested repurposing hypothesis in renal pathology."
            )

        tinfo = trials_by_name.get(ent.lower())
        trial_clause = ""
        if tinfo:
            trs = tinfo.get("trials") or []
            scope = f" ({tinfo['scope_note']})" if tinfo.get("scope_note") else ""
            if trs:
                t_list = "; ".join(
                    f"{'/'.join(tr.get('phases') or ['N/A'])} ({tr.get('status')}) — {tr.get('title')} [{tr['nct_id']}]"
                    for tr in trs[:2]
                )
                trial_clause = f" On ClinicalTrials.gov, {tinfo.get('total_count', len(trs))} kidney studies were identified{scope}, including {t_list}."
            else:
                trial_clause = f" No registered kidney trials were identified on ClinicalTrials.gov{scope}."

        if safe_pts:
            sf_txt = " ".join(
                f"{pt.get('finding').rstrip('.')} [PMID:{pt['pmid']}]."
                if pt.get("pmid")
                else f"{pt.get('finding').rstrip('.')}."
                for pt in safe_pts[:2]
            )
            safe_paragraphs.append(
                f"Regarding renal safety of **{ent}** ({safe_hits} nephrotoxicity/AKI hits), literature notes: {sf_txt}{trial_clause}"
            )
        else:
            safe_paragraphs.append(
                f"No direct nephrotoxicity warning abstracts were extracted for **{ent}** (safety hits={safe_hits}).{trial_clause}"
            )

    for tr_blk in trials:
        nm = str(tr_blk.get("compound") or "")
        if nm.lower() in seen_trial_ents:
            continue
        trs = tr_blk.get("trials") or []
        t_strs = "; ".join(f"{t.get('title')} [{t['nct_id']}]" for t in trs[:2])
        safe_paragraphs.append(
            f"ClinicalTrials.gov lists {tr_blk.get('total_count', 0)} kidney studies for **{nm}**: {t_strs or 'none'}."
        )

    if eff_paragraphs:
        lines.append(" ".join(eff_paragraphs))
    if safe_paragraphs:
        lines.append("")
        lines.append(" ".join(safe_paragraphs))


def _build_deterministic_synthesis(
    skill_id: str,
    artifacts: dict,
    steps: list[dict],
) -> str:
    """Zero-hallucination narrative report matching each Skill's fixed ### 1..4 sections."""
    lines: list[str] = []
    rows = artifacts.get("raw_rows") or []
    lits = artifacts.get("literature") or []
    trials = artifacts.get("clinical_trials") or []
    comp_cmp = artifacts.get("comparison")
    facts = artifacts.get("facts") or []
    prof = artifacts.get("profile") or {}
    tdiki_exp = artifacts.get("tdiki_explain") or {}
    reflections = [s["detail"] for s in steps if s.get("type") == "reflection"]

    if skill_id == "compound-compare" and comp_cmp and comp_cmp.get("compounds"):
        cps = comp_cmp["compounds"]
        hl = comp_cmp.get("highlights") or {}
        lines.append("### 1. Head-to-Head Safety & Clinical Maturity")
        names = " vs. ".join(f"**{c['pert_iname']}**" for c in cps)
        lines.append(
            f"Comparing {names}, **{hl.get('safest_kidney')}** exhibits the lowest predicted nephrotoxicity profile across NephroSafe T-DIKI v2 and FDA DIRIL."
        )
        lines.append("\n| Compound | pert_id | Phase | MoA | T-DIKI | DIRIL | ECM_fibrosis | Podocyte_slit |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for c in cps:
            rm = c.get("renal_modules") or {}
            lines.append(
                f"| {c['pert_iname']} | `{c['pert_id']}` | {c['clinical_phase']} | {c['moa']} | "
                f"{c['tdiki_tier']} ({_fmt_num(c.get('tdiki_prob'), 3)}) | {_fmt_diril(c.get('diril_label'))} | "
                f"{_fmt_num(rm.get('ECM_fibrosis'), 2)} | {_fmt_num(rm.get('Podocyte_slit'), 2)} |"
            )
        lines.append("\n### 2. Mechanistic & Renal Module Trade-offs")
        mod_parts = [
            f"**{c['pert_iname']}** shifts ECM_fibrosis={_fmt_num((c.get('renal_modules') or {}).get('ECM_fibrosis'), 2)}, "
            f"TGFb_SMAD={_fmt_num((c.get('renal_modules') or {}).get('TGFb_SMAD'), 2)}, "
            f"Podocyte_slit={_fmt_num((c.get('renal_modules') or {}).get('Podocyte_slit'), 2)}, and "
            f"PT_FAO_mito={_fmt_num((c.get('renal_modules') or {}).get('PT_FAO_mito'), 2)}"
            for c in cps
        ]
        lines.append(
            "Across curated kidney pathology modules, " + "; ".join(mod_parts)
            + f". Overall, **{hl.get('best_antifibrotic')}** provides the strongest anti-fibrotic transcriptional suppression while **{hl.get('best_podocyte_metabolic')}** best supports podocyte and mitochondrial FAO programs."
        )
        _append_literature_section(lines, lits, trials, "### 3. Integrated Literature & Clinical Review")
        lines.append("\n### 4. Context-Dependent Recommendation")
        lines.append(
            f"Select **{hl.get('safest_kidney')}** when clinical kidney safety is the primary constraint, or prioritize **{hl.get('best_antifibrotic')}** for mechanistic anti-fibrotic validation with careful renal monitoring."
        )
        return "\n".join(lines).strip()

    if skill_id == "toxicity-rescue":
        lines.append("### 1. NephroSafe Verdict & Attribution Rationale")
        if prof:
            contribs = ", ".join(
                f"`{c['feature']}` ({c['contribution']:+})"
                for c in (tdiki_exp.get("top_contributions") or [])[:4]
                if c.get("feature") and c.get("contribution") is not None
            )
            lines.append(
                f"**{prof.get('pert_iname')}** (`{prof.get('pert_id')}`, {prof.get('clinical_phase') or 'Preclinical'}, MoA: `{prof.get('moa') or '—'}`) "
                f"carries a T-DIKI v2 risk tier of **{prof.get('tdiki_tier', 'NA')}** (p={_fmt_num(prof.get('tdiki_prob'), 3)}) with FDA DIRIL status **{_fmt_diril(prof.get('diril_label'))}**."
                + (f" Attribution analysis highlights {contribs} as primary drivers of its predicted renal liability." if contribs else "")
            )
        lines.append("\n### 2. Safer Structural Analog Rescue")
        if reflections:
            lines.append(" ".join(reflections))
        if rows:
            lines.append("\n| Rank | Analog | pert_id | Tanimoto | T-DIKI | MoA |")
            lines.append("|---|---|---|---|---|---|")
            for idx, r in enumerate(rows[:3], 1):
                lines.append(
                    f"| {idx} | {r.get('pert_iname') or r.get('pert_id')} | `{r.get('pert_id')}` | "
                    f"{_fmt_num(r.get('tanimoto'), 3)} | {r.get('tdiki_tier') or 'NA'} | {_first_moa(r.get('moa'))} |"
                )
        _append_literature_section(lines, lits, trials, "### 3. Integrated Literature & Clinical Review")
        lines.append("\n### 4. Translational Recommendation & Next Steps")
        top_safe = next((r for r in rows if r.get("tdiki_tier") == "Low" and r.get("diril_label") != 1), None)
        if top_safe:
            lines.append(
                f"Evaluate **{top_safe.get('pert_iname') or top_safe.get('pert_id')}** (`{top_safe.get('pert_id')}`, T-DIKI `Low`, Tanimoto={_fmt_num(top_safe.get('tanimoto'), 3)}) as a structurally related lower-risk alternative."
            )
        else:
            lines.append("No `Low` T-DIKI structural analog was found among the top 120 ECFP4 neighbors; scaffold hopping via signature or pathway reversal screening is recommended.")
        return "\n".join(lines).strip()

    if skill_id == "literature-evidence":
        lines.append("### 1. Executive Evidence Verdict & Novelty")
        verdicts = [
            f"**{lit.get('entity')}** maps to `{lit.get('evidence_tier')}` ({lit.get('efficacy_total_hits', 0)} renal efficacy hits, {lit.get('safety_total_hits', 0)} safety hits via {lit.get('provider')}; {(lit.get('synthesis') or {}).get('novelty_note', '')})"
            for lit in lits
        ]
        lines.append(" ".join(verdicts) or "Completed literature audit.")
        _append_literature_section(lines, lits, trials, "### 2. Synthesized Kidney Efficacy Literature")
        lines.append("\n### 3. Integrated Nephrotoxicity & Clinical Trials Review")
        tr_notes = []
        for tr_blk in trials:
            trs = tr_blk.get("trials") or []
            t_list = "; ".join(f"{'/'.join(t.get('phases') or ['N/A'])} ({t.get('status')}) [{t['nct_id']}]" for t in trs[:3])
            tr_notes.append(f"**{tr_blk.get('compound')}**: {tr_blk.get('total_count', 0)} registered kidney studies ({t_list or 'none'}).")
        lines.append(" ".join(tr_notes) or "ClinicalTrials.gov returned no kidney studies for the audited entity.")
        lines.append("\n### 4. Translational Takeaway")
        lines.append("Synthesized findings above are verified directly against live Europe PMC/PubMed and ClinicalTrials.gov records; see the numbered References below for full citations.")
        return "\n".join(lines).strip()

    sec_titles = {
        "target-to-lead": (
            "### 1. Target Nephron Biology & Direct Drugs",
            "### 2. Knockdown-Mimicking Leads & Safety",
            "### 3. Integrated Literature & Clinical Review",
            "### 4. Translational Recommendation & Next Steps",
        ),
        "structure-moa-evidence": (
            "### 1. Chemical Neighborhood & Consensus MoA",
            "### 2. Closest Neighbor Safety & Kidney Profile",
            "### 3. Integrated Literature & Clinical Review",
            "### 4. Translational Recommendation & Next Steps",
        ),
    }.get(
        skill_id,
        (
            "### 1. Executive Synthesis & Prioritized Candidates",
            "### 2. Mechanistic & NephroSafe Rationale",
            "### 3. Integrated Literature & Clinical Review",
            "### 4. Translational Recommendation & Next Steps",
        ),
    )

    lines.append(sec_titles[0])
    summary_intro = " · ".join(f"{f['label']}: {f['value']}" for f in facts[:4]) if facts else ""
    ref_clause = (" " + " ".join(reflections)) if reflections else ""
    lines.append(f"Deterministic screening completed ({summary_intro}).{ref_clause}".strip())
    if rows:
        score_lbl = (
            "RTPS" if rows[0].get("rtps") is not None
            else "Score" if rows[0].get("pathway_tf_score") is not None
            else "Tanimoto" if rows[0].get("tanimoto") is not None
            else "Cosine"
        )
        lines.append(f"\n| Rank | Compound | pert_id | {score_lbl} | T-DIKI | DIRIL | Phase |")
        lines.append("|---|---|---|---|---|---|---|")
        for idx, r in enumerate(rows[:3], 1):
            sc = (
                _fmt_num(r.get("rtps"), 1) if r.get("rtps") is not None
                else _fmt_num(r.get("pathway_tf_score"), 2) if r.get("pathway_tf_score") is not None
                else _fmt_num(r.get("tanimoto"), 3) if r.get("tanimoto") is not None
                else _fmt_num(r.get("similarity"), 3)
            )
            lines.append(
                f"| {idx} | {r.get('pert_iname') or r.get('pert_id')} | `{r.get('pert_id')}` | {sc} | "
                f"{r.get('tdiki_tier') or 'NA'} | {_fmt_diril(r.get('diril_label'))} | {r.get('clinical_phase') or 'Preclinical'} |"
            )

    lines.append(f"\n{sec_titles[1]}")
    if prof:
        pws = ", ".join(f"{k} ({v})" for k, v in list((prof.get("top_progeny") or {}).items())[:4]) or "none"
        mods = ", ".join(f"{k} ({v})" for k, v in list((prof.get("top_renal_modules") or {}).items())[:3]) or "none"
        tgs = ", ".join((prof.get("targets") or [])[:5]) or "unannotated"
        lines.append(
            f"The top profiled candidate **{prof.get('pert_iname')}** (`{prof.get('pert_id')}`) acts via `{prof.get('moa') or 'unannotated MoA'}` "
            f"(targets: {tgs}) with a NephroSafe T-DIKI tier of **{prof.get('tdiki_tier', 'NA')}** (p={_fmt_num(prof.get('tdiki_prob'), 3)}). "
            f"In K-PRL kidney context, its strongest PROGENy pathway shifts are {pws}, alongside renal module activities in {mods}."
        )
    else:
        lines.append("Review the ranked candidates table and supporting evidence tabs below for detailed pathway and K-PRL metrics.")

    _append_literature_section(lines, lits, trials, sec_titles[2])

    lines.append(f"\n{sec_titles[3]}")
    safe_cands = _first_safe_candidates(rows, limit=1)
    if safe_cands:
        pid, nm = safe_cands[0]
        lit0 = next((l for l in lits if str(l.get("entity", "")).lower() == nm.lower()), None)
        tier_note = f" backed by `{lit0['evidence_tier']}` literature evidence" if lit0 else ""
        lines.append(
            f"Prioritize **{nm}** (`{pid}`){tier_note} for head-to-head comparison against #2 and targeted renal validation."
        )
    else:
        lines.append("Review the ranked candidates and verified References below to select leads for follow-up.")

    return "\n".join(lines).strip()


def _build_dynamic_suggestions(skill_id: str, session_state: dict, artifacts: dict) -> list[str]:
    suggestions: list[str] = []
    cands = session_state.get("candidates") or []
    lits = artifacts.get("literature") or []

    if len(cands) >= 2 and skill_id != "compound-compare":
        c1 = cands[0].get("pert_iname") or cands[0].get("pert_id")
        c2 = cands[1].get("pert_iname") or cands[1].get("pert_id")
        suggestions.append(f"Compare #1 ({c1}) and #2 ({c2}) head-to-head on fibrosis & safety")

    toxic_hit = next(
        (c for c in cands[:4] if c.get("tdiki_tier") == "High" or c.get("diril_label") == 1),
        None,
    )
    if toxic_hit and skill_id != "toxicity-rescue":
        nm = toxic_hit.get("pert_iname") or toxic_hit.get("pert_id")
        suggestions.append(f"Explain {nm} T-DIKI drivers and find safer Low-DIKI structural analogs")

    if cands and skill_id != "literature-evidence":
        if len(cands) >= 3:
            c3 = cands[2].get("pert_iname") or cands[2].get("pert_id")
            suggestions.append(f"Check Europe PMC literature and clinical trials for #3 ({c3})")
        elif len(cands) >= 1:
            c1 = cands[0].get("pert_iname") or cands[0].get("pert_id")
            suggestions.append(f"Deep-audit nephrotoxicity papers and clinical trials for {c1}")

    novel_lit = next((l for l in lits if str(l.get("evidence_tier", "")).startswith("Novel")), None)
    if novel_lit:
        ent = novel_lit.get("entity")
        suggestions.append(f"Find approved structural analogs of {ent} to cross-validate MoA")

    if not suggestions:
        suggestions = [
            "Find reversal drugs for the DKD glomeruli case and verify literature",
            "Is tacrolimus nephrotoxic? Check safety papers and find safer Low-DIKI analogs",
            "Compare dexamethasone and losartan on renal fibrosis and podocyte safety",
        ]
    return suggestions[:3]


# ---------------------------------------------------------------------------
# Deterministic Multi-Step Auto-Research Pipeline (0-LLM / Quota Fallback)
# ---------------------------------------------------------------------------
def _run_deterministic_skill(
    query: str,
    skill,
    route_meta: dict,
    tools: dict,
    session_state: dict,
    pool: EvidencePool,
    include_literature: bool,
    emit,
    cancel_event: threading.Event | None,
) -> tuple[dict, list[dict]]:
    steps: list[dict] = []
    artifacts: dict = {
        "literature": [],
        "clinical_trials": [],
        "links": [],
        "facts": [],
        "table": {"columns": [], "rows": []},
        "kprl_table": None,
        "comparison": None,
        "raw_rows": [],
    }
    step_no = 0

    def cancelled() -> bool:
        return bool(cancel_event and cancel_event.is_set())

    def call_and_emit(tool_name: str, args: dict):
        nonlocal step_no
        if cancelled():
            return None
        step_no += 1
        t0 = time.perf_counter()
        args_brief = ", ".join(f"{k}={str(v)[:36]}" for k, v in args.items() if v is not None)
        emit("tool_start", {"step": step_no, "tool": tool_name, "args": args_brief})
        digest, ui, summary = _execute_tool(
            tool_name, args, tools, session_state, pool, include_literature
        )
        ms = _ms(t0)
        if ui.get("table") and ui["table"].get("rows"):
            artifacts["table"] = ui["table"]
        if ui.get("raw_rows"):
            artifacts["raw_rows"] = ui["raw_rows"]
        if ui.get("facts"):
            artifacts["facts"] = ui["facts"]
        if ui.get("kprl_table"):
            artifacts["kprl_table"] = ui["kprl_table"]
        if ui.get("comparison"):
            artifacts["comparison"] = ui["comparison"]
        if ui.get("literature"):
            artifacts["literature"].append(ui["literature"])
        if ui.get("clinical_trials"):
            artifacts["clinical_trials"].append(ui["clinical_trials"])
        for lk in ui.get("links") or []:
            if lk not in artifacts["links"]:
                artifacts["links"].append(lk)

        step_rec = {"step": step_no, "type": "tool", "name": tool_name, "tool": tool_name, "status": "done", "detail": summary, "ms": ms}
        steps.append(step_rec)
        emit("tool_result", {"step": step_no, "tool": tool_name, "status": "done", "ms": ms, "detail": summary, **ui})
        return digest

    sop_hint = route_meta.get("sop_hint")
    params = route_meta.get("route_params") or {}
    disease_ctx = session_state.get("active_disease") or "kidney disease"

    if skill.id == "disease-repurposing":
        emit("thinking", {"text": f"Running initial computational screen ({sop_hint or 'disease screen'}), then auditing top candidates for NephroSafe risk."})
        d1 = None
        if sop_hint == "SOP-6" or params.get("case_id"):
            cid_hint = params.get("case_id") or query
            d1 = call_and_emit("run_cohort_case", {"case_id": cid_hint, "top_k": 15})
            if d1:
                disease_ctx = d1.get("disease") or disease_ctx
        elif sop_hint == "SOP-3" or params.get("targets"):
            targets = params.get("targets") or {"SMAD3": -1, "PPARA": 1}
            d1 = call_and_emit("query_pathway_tf", {"targets": targets, "top_k": 15})
            disease_ctx = "renal fibrosis"
        else:
            up = params.get("up_genes") or []
            dn = params.get("down_genes") or []
            if not up and not dn:
                raise ValueError("Please specify a cohort (e.g. DKD), pathway targets, or Up:/Down: gene lists.")
            flt = params.get("filters") or {}
            d1 = call_and_emit(
                "score_gene_signature",
                {
                    "up_genes": up,
                    "down_genes": dn,
                    "context": params.get("context") or "kprl",
                    "kidney_compartment": params.get("kidney_compartment"),
                    "approved_only": bool(flt.get("approved_only")),
                    "max_diki_tier": flt.get("max_diki_tier"),
                    "top_k": 15,
                },
            )
            disease_ctx = "kidney fibrosis"

        if cancelled():
            return artifacts, steps

        # Reflect on top-3 safety
        rows = artifacts.get("raw_rows") or []
        toxic_top = [
            r.get("pert_iname") or r.get("pert_id")
            for r in rows[:3]
            if r.get("tdiki_tier") == "High" or r.get("diril_label") == 1
        ]
        already_safe_filtered = bool((d1 or {}).get("filters", {}).get("max_diki_tier") == "Low")
        if toxic_top and not already_safe_filtered:
            ref_txt = (
                f"Detected high nephrotoxicity risk in top hits ({', '.join(toxic_top)}). "
                "Triggering safety re-screen for Approved + Low T-DIKI candidates."
            )
            emit("reflection", {"text": ref_txt})
            steps.append({"step": step_no + 0.5, "type": "reflection", "name": "Safety reflection", "tool": "nephrosafe_policy", "status": "done", "detail": ref_txt, "ms": 0.0})
            if sop_hint == "SOP-6" and d1 and d1.get("case_id"):
                call_and_emit("run_cohort_case", {"case_id": d1["case_id"], "approved_only": True, "max_diki_tier": "Low", "top_k": 15})
            elif sop_hint == "SOP-1":
                call_and_emit("score_gene_signature", {
                    "up_genes": params.get("up_genes") or [],
                    "down_genes": params.get("down_genes") or [],
                    "context": params.get("context") or "kprl",
                    "approved_only": True,
                    "max_diki_tier": "Low",
                    "top_k": 15,
                })
            elif rows:
                top_nm = rows[0].get("pert_iname") or rows[0].get("pert_id")
                call_and_emit("find_safe_analogs", {"compound": top_nm, "max_diki_tier": "Low", "top_k": 10})

        if cancelled():
            return artifacts, steps

        safe_cands = _first_safe_candidates(artifacts.get("raw_rows") or [], limit=2)
        if safe_cands:
            pid0, nm0 = safe_cands[0]
            emit("thinking", {"text": f"Profiling #1 candidate ({nm0} [{pid0}]) and synthesizing real-world kidney literature & clinical trials."})
            artifacts["profile"] = call_and_emit("profile_compound", {"token": pid0})
            if include_literature and not cancelled():
                for _pid, nm in safe_cands:
                    call_and_emit("search_literature", {"entity": nm, "disease_context": disease_ctx, "include_safety": True, "max_papers": 5})
                    call_and_emit("search_clinical_trials", {"compound": nm, "condition": disease_ctx, "max_trials": 4})

    elif skill.id == "toxicity-rescue":
        refs = resolve_session_references(query, session_state, tools["find_compound"])
        tok = refs[0] if refs else (params.get("compound") or "")
        if not tok:
            cands = _extract_compound_candidates(query)
            tok = cands[0] if cands else query.strip()
        emit("thinking", {"text": f"Auditing NephroSafe risk for '{tok}' and checking structural rescue options."})
        prof = call_and_emit("profile_compound", {"token": tok})
        artifacts["profile"] = prof
        target_name = (prof or {}).get("pert_iname") or tok
        target_pid = (prof or {}).get("pert_id") or target_name
        if not cancelled():
            artifacts["tdiki_explain"] = call_and_emit("explain_tdiki", {"token": target_pid, "top_n": 8})
        need_rescue = (
            (prof or {}).get("tdiki_tier") in ("High", "Moderate")
            or (prof or {}).get("diril_label") == 1
            or bool(re.search(r"analog|safer|rescue|alternative|替代|类似", query, re.I))
        )
        if need_rescue and not cancelled():
            ref_txt = f"{target_name} shows T-DIKI={(prof or {}).get('tdiki_tier', 'NA')} / DIRIL={(prof or {}).get('diril_label')}; scanning 21,299 ECFP4 compounds for Low T-DIKI structural analogs."
            emit("reflection", {"text": ref_txt})
            steps.append({"step": step_no + 0.5, "type": "reflection", "name": "Toxicity rescue", "tool": "nephrosafe_policy", "status": "done", "detail": ref_txt, "ms": 0.0})
            call_and_emit("find_safe_analogs", {"compound": target_pid, "max_diki_tier": "Low", "top_k": 10})
        if include_literature and not cancelled():
            call_and_emit("search_literature", {"entity": target_name, "disease_context": disease_ctx, "include_safety": True, "max_papers": 6})
            call_and_emit("search_clinical_trials", {"compound": target_name, "condition": disease_ctx, "max_trials": 4})

    elif skill.id == "target-to-lead":
        gene = params.get("gene") or ""
        if not gene:
            m_g = re.findall(r"\b([A-Z][A-Z0-9]{1,8})\b", query)
            gene = next((g for g in m_g if g not in {"SOP", "MCP", "DNA", "RNA", "ECFP4", "LINCS"}), "")
        if not gene:
            raise ValueError("Please provide a human target gene symbol (e.g. TGFBR1).")
        emit("thinking", {"text": f"Inspecting nephron expression & knockdown mimics for {gene}, then auditing the lead candidate."})
        t_dig = call_and_emit("profile_target", {"symbol": gene, "top_k": 15})
        mimics = (t_dig or {}).get("mimicking_compounds") or []
        lead_rec = next((m for m in mimics if m.get("pert_iname") and m.get("pert_id")), None)
        if lead_rec and not cancelled():
            artifacts["profile"] = call_and_emit("profile_compound", {"token": lead_rec["pert_id"]})
        if include_literature and not cancelled():
            call_and_emit("search_literature", {"entity": gene, "disease_context": disease_ctx, "include_safety": False, "max_papers": 4})
            if lead_rec:
                call_and_emit("search_literature", {"entity": lead_rec["pert_iname"], "disease_context": disease_ctx, "include_safety": True, "max_papers": 4})
                call_and_emit("search_clinical_trials", {"compound": lead_rec["pert_iname"], "condition": disease_ctx, "max_trials": 3})

    elif skill.id == "structure-moa-evidence":
        smiles = params.get("smiles")
        pid = params.get("pert_id")
        if not smiles and not pid:
            cands = resolve_session_references(query, session_state, tools["find_compound"])
            pid = cands[0] if cands else None
        if not smiles and not pid:
            raise ValueError("Please specify a SMILES string, compound name, or BRD ID.")
        emit("thinking", {"text": "Scanning 21,299 ECFP4 fingerprints for consensus MoA and checking literature on the top neighbor."})
        s_dig = call_and_emit("find_safe_analogs", {"smiles": smiles, "compound": pid, "top_k": 12})
        hits = (s_dig or {}).get("results") or []
        top_hit = next((h for h in hits if h.get("pert_iname") and h.get("pert_id")), None)
        if top_hit and not cancelled():
            artifacts["profile"] = call_and_emit("profile_compound", {"token": top_hit["pert_id"]})
            if include_literature and not cancelled():
                call_and_emit("search_literature", {"entity": top_hit["pert_iname"], "disease_context": disease_ctx, "include_safety": True, "max_papers": 5})

    elif skill.id == "literature-evidence":
        entities = resolve_session_references(query, session_state, tools["find_compound"])
        if not entities:
            m_g = re.findall(r"\b([A-Z][A-Z0-9]{2,8})\b", query)
            entities = [g for g in m_g if g not in {"PMID", "NCT", "SOP", "EPMC"}][:2]
        if not entities:
            raise ValueError("Specify a drug or gene name (or refer to #1/#2 from the active results).")
        emit("thinking", {"text": f"Running bidirectional kidney efficacy + nephrotoxicity literature and ClinicalTrials.gov audit for {', '.join(entities[:2])}."})
        for ent in entities[:2]:
            if cancelled():
                break
            call_and_emit("search_literature", {"entity": ent, "disease_context": disease_ctx, "include_safety": True, "max_papers": 6})
            call_and_emit("search_clinical_trials", {"compound": ent, "condition": disease_ctx, "max_trials": 5})

    elif skill.id == "compound-compare":
        tokens = resolve_session_references(query, session_state, tools["find_compound"])
        if len(tokens) < 2:
            cands = session_state.get("candidates") or []
            for c in cands:
                nm = c.get("pert_iname") or c.get("pert_id")
                if nm and nm not in tokens:
                    tokens.append(nm)
                if len(tokens) >= 2:
                    break
        if len(tokens) < 2:
            raise ValueError("Please provide at least 2 compounds to compare (e.g. 'Compare dexamethasone and losartan' or '#1 and #2').")
        emit("thinking", {"text": f"Running head-to-head comparison across NephroSafe risk, PROGENy pathways, and 9 renal modules for {', '.join(tokens[:4])}."})
        cmp_dig = call_and_emit("compare_compounds", {"compounds": tokens[:4]})
        if include_literature and cmp_dig and not cancelled():
            for cp in (cmp_dig.get("compounds") or [])[:2]:
                if cancelled():
                    break
                nm = cp["pert_iname"]
                if nm.lower() not in (session_state.get("literature_by_entity") or {}):
                    call_and_emit("search_literature", {"entity": nm, "disease_context": disease_ctx, "include_safety": True, "max_papers": 4})
                    call_and_emit("search_clinical_trials", {"compound": nm, "condition": disease_ctx, "max_trials": 3})

    return artifacts, steps


# ---------------------------------------------------------------------------
# DeepSeek ReAct Multi-Step Loop
# ---------------------------------------------------------------------------
def _run_deepseek_react(
    query: str,
    skill,
    tools: dict,
    session_state: dict,
    pool: EvidencePool,
    include_literature: bool,
    client_ip: str,
    emit,
    cancel_event: threading.Event | None,
) -> tuple[str, dict, list[dict], dict, bool]:
    """Execute bounded ReAct tool loop via DeepSeek; returns (summary, artifacts, steps, usage, fallback_used)."""
    from openai import OpenAI

    policy = get_policy()
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    client = OpenAI(api_key=api_key, base_url=policy.base_url, timeout=25.0)

    sys_prompt = build_system_prompt(skill, session_state, include_literature=include_literature)
    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": query},
    ]

    allowed_names = list(skill.allowed_tools)
    if not include_literature:
        allowed_names = [t for t in allowed_names if t not in ("search_literature", "search_clinical_trials")]
    tool_defs = [TOOL_SCHEMAS[t] for t in allowed_names if t in TOOL_SCHEMAS]

    max_iters = min(skill.max_steps, policy.max_steps_ceiling)
    t_start = time.perf_counter()
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    quota_recorded = False
    called_keys: set[str] = set()
    used_tool_names: set[str] = set()
    steps: list[dict] = []
    artifacts: dict = {
        "literature": [],
        "clinical_trials": [],
        "links": [],
        "facts": [],
        "table": {"columns": [], "rows": []},
        "kprl_table": None,
        "comparison": None,
        "raw_rows": [],
    }
    step_no = 0
    draft_answer = ""
    nudge_sent = False

    def call_llm(with_tools: bool, max_tok: int):
        nonlocal quota_recorded
        kwargs = {
            "model": policy.model,
            "messages": messages,
            "temperature": policy.temperature,
            "top_p": policy.top_p,
            "seed": policy.seed,
            "max_tokens": max_tok,
        }
        if with_tools and tool_defs:
            kwargs["tools"] = tool_defs
            kwargs["tool_choice"] = "auto"
        resp = client.chat.completions.create(**kwargs)
        if not quota_recorded:
            record_llm_usage(client_ip)
            quota_recorded = True
        u = getattr(resp, "usage", None)
        if u is not None:
            usage["prompt_tokens"] += int(getattr(u, "prompt_tokens", 0) or 0)
            usage["completion_tokens"] += int(getattr(u, "completion_tokens", 0) or 0)
            usage["total_tokens"] += int(getattr(u, "total_tokens", 0) or 0)
        return resp.choices[0].message, getattr(resp.choices[0], "finish_reason", "stop")

    for it in range(max_iters):
        if cancel_event and cancel_event.is_set():
            break
        if (time.perf_counter() - t_start) > policy.max_wall_seconds:
            emit("thinking", {"text": "Wall-clock budget reached; synthesizing grounded report from collected evidence."})
            break
        if usage["prompt_tokens"] > policy.max_prompt_tokens:
            emit("thinking", {"text": "Token budget reached; finalizing report cleanly."})
            break

        is_last = it == (max_iters - 1)
        msg, finish_reason = call_llm(
            with_tools=(not is_last),
            max_tok=policy.max_tokens_synthesis if is_last else policy.max_tokens_step,
        )
        content = (msg.content or "").strip()
        tool_calls = getattr(msg, "tool_calls", None) or []

        if not tool_calls:
            # Guard: ensure the agent actually used tools before finalizing
            if not used_tool_names and not nudge_sent:
                nudge_sent = True
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": "Execute the required tool(s) for this Skill first before writing the final answer.",
                })
                continue
            # Guard: nudge once for missing literature if Skill requires it and budget remains
            if (
                include_literature
                and skill.requires_literature
                and "search_literature" in allowed_names
                and "search_literature" not in used_tool_names
                and not nudge_sent
                and it < max_iters - 1
            ):
                nudge_sent = True
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": "Before finalizing, call search_literature (and search_clinical_trials if relevant) on your top 1-2 candidate(s) so claims are backed by real PMIDs/NCTs.",
                })
                continue
            if finish_reason == "length" and content:
                messages.append({"role": "assistant", "content": content})
                messages.append({
                    "role": "user",
                    "content": "Your previous draft hit the length limit. Rewrite concisely (<= 240 words) completing ALL required ### 1..4 sections from the Skill template, including Literature & Clinical Synthesis with [PMID:...] citations.",
                })
                msg2, _ = call_llm(with_tools=False, max_tok=policy.max_tokens_synthesis)
                content = (msg2.content or "").strip() or content
            draft_answer = content
            break

        if content:
            emit("thinking", {"text": content[:280]})

        messages.append({
            "role": "assistant",
            "content": content or "",
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in tool_calls[:3]
            ],
        })

        for tc in tool_calls[:3]:
            if cancel_event and cancel_event.is_set():
                break
            tname = tc.function.name
            try:
                targs = json.loads(tc.function.arguments or "{}")
            except Exception:
                targs = {}

            if tname not in allowed_names:
                err_json = json.dumps({"error": f"Tool '{tname}' is not allowed in skill '{skill.id}'."})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": err_json})
                continue

            ckey = canonical_call_key(tname, targs)
            if ckey in called_keys:
                dup_json = json.dumps({"note": "Duplicate tool call skipped; reuse the earlier observation."})
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": dup_json})
                continue
            called_keys.add(ckey)

            step_no += 1
            t0 = time.perf_counter()
            args_brief = ", ".join(f"{k}={str(v)[:36]}" for k, v in targs.items() if v is not None)
            emit("tool_start", {"step": step_no, "tool": tname, "args": args_brief})
            try:
                digest, ui, summary = _execute_tool(
                    tname, targs, tools, session_state, pool, include_literature
                )
                used_tool_names.add(tname)
                ms = _ms(t0)
                if ui.get("table") and ui["table"].get("rows"):
                    artifacts["table"] = ui["table"]
                if ui.get("raw_rows"):
                    artifacts["raw_rows"] = ui["raw_rows"]
                if ui.get("facts"):
                    artifacts["facts"] = ui["facts"]
                if ui.get("kprl_table"):
                    artifacts["kprl_table"] = ui["kprl_table"]
                if ui.get("comparison"):
                    artifacts["comparison"] = ui["comparison"]
                if ui.get("literature"):
                    artifacts["literature"].append(ui["literature"])
                if ui.get("clinical_trials"):
                    artifacts["clinical_trials"].append(ui["clinical_trials"])
                if tname == "profile_compound":
                    artifacts["profile"] = digest
                elif tname == "explain_tdiki":
                    artifacts["tdiki_explain"] = digest
                for lk in ui.get("links") or []:
                    if lk not in artifacts["links"]:
                        artifacts["links"].append(lk)

                steps.append({"step": step_no, "type": "tool", "name": tname, "tool": tname, "status": "done", "detail": summary, "ms": ms})
                emit("tool_result", {"step": step_no, "tool": tname, "status": "done", "ms": ms, "detail": summary, **ui})
                obs = compact_digest(digest, max_chars=policy.tool_digest_max_chars)
            except Exception as exc:
                ms = _ms(t0)
                err_msg = getattr(exc, "detail", None) or str(exc)
                steps.append({"step": step_no, "type": "tool", "name": tname, "tool": tname, "status": "error", "detail": err_msg[:180], "ms": ms})
                emit("tool_result", {"step": step_no, "tool": tname, "status": "error", "ms": ms, "detail": err_msg[:180]})
                obs = json.dumps({"error": err_msg[:220]})

            messages.append({"role": "tool", "tool_call_id": tc.id, "content": obs})

    if not draft_answer and not (cancel_event and cancel_event.is_set()):
        try:
            msg, _ = call_llm(with_tools=False, max_tok=policy.max_tokens_synthesis)
            draft_answer = (msg.content or "").strip()
        except Exception:
            draft_answer = ""

    if not draft_answer:
        det_summary = _build_deterministic_synthesis(skill.id, artifacts, steps)
        ver = verify_grounded_response(det_summary, pool)
        ver["mode"] = "deterministic_fallback"
        return det_summary, artifacts, steps, usage, True

    # Strict PMID / NCT / BRD / float grounding verification + 1x repair
    ver = verify_grounded_response(draft_answer, pool)
    if not ver["verified"]:
        emit("reflection", {"text": f"Citation/numeric verifier flagged: {'; '.join(ver['hard_violations'])}. Running 1x grounding repair."})
        try:
            messages.append({"role": "assistant", "content": draft_answer})
            messages.append({"role": "user", "content": build_repair_prompt(draft_answer, ver["hard_violations"], pool)})
            rep_msg, _ = call_llm(with_tools=False, max_tok=policy.max_tokens_repair)
            repaired = (rep_msg.content or "").strip()
            ver2 = verify_grounded_response(repaired, pool)
            if ver2["verified"]:
                ver2["repaired"] = True
                return repaired, artifacts, steps, usage, False
        except Exception:
            pass
        det_summary = _build_deterministic_synthesis(skill.id, artifacts, steps)
        return det_summary, artifacts, steps, usage, True

    return draft_answer, artifacts, steps, usage, False


# ---------------------------------------------------------------------------
# Public Entry Point for Real-Time SSE Streaming & Sync Collection
# ---------------------------------------------------------------------------
def execute_agent_stream(
    query: str,
    tools: dict,
    emit,
    session_id: str | None = None,
    mode: str = "auto",
    skill_id: str | None = None,
    include_literature: bool = True,
    client_ip: str = "local",
    cancel_event: threading.Event | None = None,
) -> dict:
    """Execute one multi-step turn, invoking `emit(event_name, data_dict)` in real time."""
    t_total = time.perf_counter()
    clean_q = (query or "").strip()
    session_state = load_session(session_id)
    sid = session_state["session_id"]

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    quota = check_llm_quota(client_ip)
    req_mode = (mode or "auto").lower()
    use_deepseek = req_mode != "fast" and bool(api_key) and bool(quota["allowed"])
    quota_notice = None
    if req_mode != "fast":
        if not api_key:
            quota_notice = "Server DEEPSEEK_API_KEY not configured; executing deterministic multi-step pipeline."
        elif not quota["allowed"]:
            quota_notice = quota["reason"]

    mode_effective = "deepseek_react" if use_deepseek else "deterministic_multistep"

    emit("session", {
        "session_id": sid,
        "mode_requested": req_mode,
        "mode_effective": mode_effective,
        "quota": quota,
        "quota_notice": quota_notice,
    })

    if not clean_q:
        payload = {
            "session_id": sid,
            "query": clean_q,
            "status": "needs_input",
            "mode_effective": mode_effective,
            "summary": "Enter a kidney drug-repurposing research question or choose a playbook below.",
            "suggestions": [
                "Find reversal drugs for the DKD glomeruli case and verify literature & clinical trials",
                "Is tacrolimus nephrotoxic? Check safety papers and find safer Low-DIKI analogs",
                "Compare dexamethasone and losartan head-to-head on fibrosis and podocyte safety",
            ],
            "elapsed_ms": _ms(t_total),
        }
        emit("done", payload)
        return payload

    skill, route_meta = select_skill(clean_q, session_state=session_state, preferred_skill=skill_id)
    if skill is None:
        emit("skill_selected", {"skill_id": "out_of_scope", "skill_name": "Scope Guardrail", "reason": route_meta.get("reason")})
        payload = {
            "session_id": sid,
            "query": clean_q,
            "status": "out_of_scope",
            "skill_id": "out_of_scope",
            "skill_name": "Scope Guardrail",
            "mode_effective": mode_effective,
            "summary": route_meta.get("reason") or "This question is outside NephroPerturb's kidney drug-repurposing scope.",
            "links": [{"label": "Browse Cohorts", "href": "/cases/"}, {"label": "Signature Workbench", "href": "/workbench/"}],
            "suggestions": [
                "Find reversal drugs for the DKD glomeruli case and verify literature",
                "Is tacrolimus nephrotoxic? Find safer Low T-DIKI analogs",
                "Compare dexamethasone and losartan",
            ],
            "elapsed_ms": _ms(t_total),
        }
        emit("done", payload)
        return payload

    emit("skill_selected", {
        "skill_id": skill.id,
        "skill_name": skill.name,
        "short_label": skill.short_label,
        "color": skill.color,
        "reason": route_meta.get("reason"),
        "max_steps": skill.max_steps,
        "allowed_tools": list(skill.allowed_tools),
    })

    # Seed EvidencePool with session ledger so follow-up citations verify cleanly
    pool = EvidencePool()
    pool.ingest({
        "candidates": session_state.get("candidates") or [],
        "pmids": session_state.get("pmids") or [],
        "ncts": session_state.get("ncts") or [],
        "literature_by_entity": session_state.get("literature_by_entity") or {},
    })

    summary = ""
    artifacts: dict = {}
    steps: list[dict] = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    fallback_used = False
    llm_error = None

    if use_deepseek:
        try:
            summary, artifacts, steps, usage, fallback_used = _run_deepseek_react(
                clean_q, skill, tools, session_state, pool, include_literature,
                client_ip, emit, cancel_event,
            )
        except Exception as exc:
            llm_error = str(exc)[:180]
            mode_effective = "deterministic_fallback"
            emit("reflection", {"text": f"DeepSeek API error ({llm_error}); switching cleanly to deterministic multi-step pipeline."})
            use_deepseek = False

    if not use_deepseek:
        try:
            artifacts, steps = _run_deterministic_skill(
                clean_q, skill, route_meta, tools, session_state, pool,
                include_literature, emit, cancel_event,
            )
            summary = _build_deterministic_synthesis(skill.id, artifacts, steps)
        except Exception as exc:
            err_detail = getattr(exc, "detail", None) or str(exc)
            payload = {
                "session_id": sid,
                "query": clean_q,
                "status": "error",
                "skill_id": skill.id,
                "skill_name": skill.name,
                "mode_effective": mode_effective,
                "summary": f"Execution stopped: {err_detail}",
                "elapsed_ms": _ms(t_total),
            }
            emit("done", payload)
            return payload

    if cancel_event and cancel_event.is_set():
        payload = {
            "session_id": sid,
            "query": clean_q,
            "status": "stopped",
            "skill_id": skill.id,
            "skill_name": skill.name,
            "mode_effective": mode_effective,
            "summary": summary or "Stopped by user.",
            "elapsed_ms": _ms(t_total),
        }
        emit("done", payload)
        return payload

    verification = verify_grounded_response(summary, pool)
    if fallback_used or not use_deepseek:
        verification["mode"] = "deterministic_fallback" if llm_error or fallback_used else "deterministic"
    emit("verification", verification)

    # Persist concise turn summary to multi-turn Session Ledger
    session_state.setdefault("turns", []).append({
        "query": clean_q[:160],
        "skill_id": skill.id,
        "short_outcome": summary.replace("\n", " ")[:180],
    })
    save_session(session_state)

    suggestions = _build_dynamic_suggestions(skill.id, session_state, artifacts)
    references = _build_references(summary, artifacts)
    new_quota = check_llm_quota(client_ip)

    payload = {
        "session_id": sid,
        "query": clean_q,
        "status": "ok",
        "skill_id": skill.id,
        "skill_name": skill.name,
        "short_label": skill.short_label,
        "color": skill.color,
        "mode_requested": req_mode,
        "mode_effective": "deterministic_fallback" if fallback_used else mode_effective,
        "quota_notice": quota_notice or (f"DeepSeek fallback: {llm_error}" if llm_error else None),
        "quota": new_quota,
        "steps": steps,
        "facts": artifacts.get("facts") or [],
        "table": artifacts.get("table") or {"columns": [], "rows": []},
        "kprl_table": artifacts.get("kprl_table"),
        "comparison": artifacts.get("comparison"),
        "literature": artifacts.get("literature") or [],
        "clinical_trials": artifacts.get("clinical_trials") or [],
        "references": references,
        "links": artifacts.get("links") or [],
        "summary": summary,
        "verification": verification,
        "usage": usage,
        "suggestions": suggestions,
        "session_snapshot": {
            "active_disease": session_state.get("active_disease"),
            "active_case_id": session_state.get("active_case_id"),
            "n_candidates": len(session_state.get("candidates") or []),
            "n_turns": len(session_state.get("turns") or []),
        },
        "elapsed_ms": _ms(t_total),
    }
    emit("done", payload)
    return payload


def stream_agent_events(
    query: str,
    tools: dict,
    session_id: str | None = None,
    mode: str = "auto",
    skill_id: str | None = None,
    include_literature: bool = True,
    client_ip: str = "local",
    cancel_event: threading.Event | None = None,
):
    """Synchronous generator convenience wrapper yielding `(event_name, data_dict)`."""
    events: list[tuple[str, dict]] = []
    execute_agent_stream(
        query, tools, lambda ev, data: events.append((ev, data)),
        session_id=session_id, mode=mode, skill_id=skill_id,
        include_literature=include_literature, client_ip=client_ip,
        cancel_event=cancel_event,
    )
    for item in events:
        yield item
