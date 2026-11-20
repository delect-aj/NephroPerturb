"""Deterministic scoring engine (scoring v2 + Lite gene-major runtime support).

Direction convention: every raw score is REVERSAL-POSITIVE (a high score means
the compound reverses the disease signature). Calibration is an empirical
signed percentile (tau in [-100, 100]) against a 600-signature real-biology
background library built offline per context.
"""
import hashlib
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yaml

from ..core.store import CONFIG, get_store

METHODS = ("xsum", "zhang", "wtcs", "func")
DEFAULT_WEIGHTS = {"xsum": 0.25, "zhang": 0.25, "wtcs": 0.25, "func": 0.25}
EXTREME_TOP_N = 500
FUNC_MIN_N = 5
FUNC_BLOCK_WEIGHTS = {"pw": 0.40, "tf": 0.30, "mod": 0.30}
COMPARTMENT_COLUMNS = {
    "podocyte": "podocyte", "pt": "pt", "tal": "tal", "dct": "dct", "cd": "cd",
    "endo": "endo", "immune": "immune", "glomerulus": "glomerulus",
    "tubule": "tubule", "whole_kidney": "whole_kidney",
}
ENGINE_VERSION = "scoring-v2.1-branchA-routing"


def _time01_contexts(disease, compartment):
    """Pre-registered compartment routing (decision gate, branch A)."""
    c = (compartment or "").lower()
    if disease in ("LN", "IgAN", "FSGS"):
        return ["renal_immune", "renal_epi"]
    if "tubul" in c:
        return ["renal_epi"]
    if disease in ("AKI", "CKD"):
        return ["renal_epi"]
    return ["pan"]


def _method_weights():
    path = CONFIG / "settings.yaml"
    try:
        cfg = yaml.safe_load(path.read_text())
        w = (cfg or {}).get("scoring", {}).get("weights") or {}
        weights = {m: float(w.get(m, DEFAULT_WEIGHTS[m])) for m in METHODS}
        total = sum(weights.values()) or 1.0
        return {m: v / total for m, v in weights.items()}
    except Exception:
        return dict(DEFAULT_WEIGHTS)


_RANK_CACHE = {}


def _ranks_for(store, context):
    key = (str(store.store), "z", context)
    if key not in _RANK_CACHE:
        name = "kprl_ranks.npy" if context == "kprl" else f"{context}_cp_ranks.npy"
        path = store.store / "matrices" / name
        if not path.exists():
            raise RuntimeError(f"{name} missing; run scripts/06_precompute_tau_bg.py")
        _RANK_CACHE[key] = np.load(path, mmap_mode="r")
    return _RANK_CACHE[key]


def _absranks_for(store, context):
    key = (str(store.store), "abs", context)
    if key not in _RANK_CACHE:
        path = store.store / "matrices" / f"{context}_absranks.npy"
        if not path.exists():
            raise RuntimeError(f"{path.name} missing; run scripts/06_precompute_tau_bg.py")
        _RANK_CACHE[key] = np.load(path, mmap_mode="r")
    return _RANK_CACHE[key]


def signed_es_sub(pos_unsorted, n_genes):
    pos = np.sort(np.asarray(pos_unsorted), axis=1).astype(np.float32)
    k = pos.shape[1]
    j = np.arange(k, dtype=np.float32)[None, :]
    misses_before = pos - j
    rs_after = (j + 1) / k - misses_before / (n_genes - k)
    rs_before = j / k - misses_before / (n_genes - k)
    hi = np.maximum(rs_after.max(axis=1), 0.0)
    lo = np.minimum(rs_before.min(axis=1), 0.0)
    return np.where(np.abs(hi) >= np.abs(lo), hi, lo)


def signed_es(ranks, idx, n_genes):
    return signed_es_sub(ranks[:, idx], n_genes)


def xsum_extreme(store, context, up_cols, dn_cols, top_n=EXTREME_TOP_N):
    if store.is_lite:
        return _score_single_context_lite(
            store, up_cols, dn_cols, None, None, context, kernels=("xsum",)
        )[0]["xsum"]
    matrix = store.matrix(context)
    ranks = _ranks_for(store, context)
    n_genes = matrix.shape[1]

    def ext(cols):
        z = np.asarray(matrix[:, cols], dtype=np.float32)
        r = np.asarray(ranks[:, cols])
        return np.where((r < top_n) | (r >= n_genes - top_n), z, 0.0).sum(axis=1)

    denom = max(len(up_cols) + len(dn_cols), 1)
    return -(ext(up_cols) - ext(dn_cols)) / denom


def zhang_score(store, context, up_cols, dn_cols):
    if store.is_lite:
        return _score_single_context_lite(
            store, up_cols, dn_cols, None, None, context, kernels=("zhang",)
        )[0]["zhang"]
    matrix = store.matrix(context)
    absranks = _absranks_for(store, context)
    n_genes = matrix.shape[1]

    def signed_mag(cols):
        z = np.asarray(matrix[:, cols], dtype=np.float32)
        ra = np.asarray(absranks[:, cols], dtype=np.float32)
        return np.sign(z) * (n_genes - ra)

    up_term = -signed_mag(up_cols).sum(axis=1)
    dn_term = signed_mag(dn_cols).sum(axis=1)
    bound = max(len(up_cols) + len(dn_cols), 1) * n_genes
    return (up_term + dn_term) / bound


def wtcs_score(store, context, up_cols, dn_cols):
    if store.is_lite:
        return _score_single_context_lite(
            store, up_cols, dn_cols, None, None, context, kernels=("wtcs",)
        )[0]["wtcs"]
    ranks = _ranks_for(store, context)
    n_genes = ranks.shape[1]
    es_up = signed_es(ranks, up_cols, n_genes)
    es_dn = signed_es(ranks, dn_cols, n_genes)
    return np.where(np.sign(es_up) * np.sign(es_dn) < 0, -(es_up - es_dn) / 2.0, 0.0)


_NET_LOOKUP = {}
_ACT_CACHE = {}


def _get_net_lookup():
    if _NET_LOOKUP:
        return _NET_LOOKUP
    net_dir = get_store().store / "annotations" / "networks"
    raw = {}
    for name, prefix in (("progeny", "pw"), ("collectri", "tf")):
        path = net_dir / f"{name}.csv"
        if path.exists():
            frame = pd.read_csv(path)
            raw[prefix] = frame[["source", "target", "weight"]]
    modules = CONFIG / "renal_modules.yaml"
    if modules.exists():
        mod = yaml.safe_load(modules.read_text())["modules"]
        rows = [{"source": k, "target": g, "weight": 1.0}
                for k, genes in mod.items() for g in genes]
        raw["mod"] = pd.DataFrame(rows)
    for prefix, df in raw.items():
        df = df.copy()
        df["target_u"] = df["target"].astype(str).str.upper()
        _NET_LOOKUP[prefix] = {
            f"{prefix}_{source}": dict(zip(sub["target_u"], sub["weight"]))
            for source, sub in df.groupby("source")
        }
    return _NET_LOOKUP


def _build_func_query_vectors(columns_by_prefix, up_symbols, down_symbols):
    lookup = _get_net_lookup()
    up = {str(s).upper() for s in up_symbols}
    down = {str(s).upper() for s in down_symbols}
    queries = {}
    for prefix, columns in columns_by_prefix.items():
        net_map = lookup.get(prefix, {})
        query = np.zeros(len(columns), dtype=np.float32)
        for col_idx, col in enumerate(columns):
            w = net_map.get(col)
            if not w:
                continue
            up_hits = [w[g] for g in up if g in w]
            dn_hits = [w[g] for g in down if g in w]
            if len(up_hits) + len(dn_hits) < FUNC_MIN_N:
                continue
            pos = sum(up_hits)
            neg = sum(dn_hits)
            norm = np.sqrt(sum(v * v for v in up_hits) + sum(v * v for v in dn_hits))
            if norm > 0:
                query[col_idx] = (pos - neg) / norm
        queries[prefix] = query
    return queries


def _block_activities(store, context):
    key = ("blocks", context)
    if key not in _ACT_CACHE:
        blocks = {}
        for name, prefix in (("progeny", "pw"), ("collectri", "tf"),
                             ("renal_modules", "mod")):
            frame = store.func_matrix(name, context)
            frame = frame.reindex(store.cp_index["pert_id"]).fillna(0.0)
            arr = frame.to_numpy(dtype=np.float32)
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            blocks[prefix] = (list(frame.columns), arr / np.maximum(norms, 1e-9))
        _ACT_CACHE[key] = blocks
    return _ACT_CACHE[key]


def func_scores(store, up_symbols, down_symbols, context="kprl"):
    if store.is_lite:
        n_genes = len(store.genes)
        return _score_single_context_lite(
            store, None, None, up_symbols, down_symbols, context,
            kernels=("func",), n_genes_override=n_genes
        )[0]["func"]
    blocks = _block_activities(store, context)
    cols_by_prefix = {p: blocks[p][0] for p in blocks}
    queries = _build_func_query_vectors(cols_by_prefix, up_symbols, down_symbols)
    combined = np.zeros(len(store.cp_index), dtype=np.float32)
    for prefix, (_, drug_acts) in blocks.items():
        query = queries[prefix]
        qn = np.linalg.norm(query)
        if qn == 0:
            continue
        cos = (drug_acts @ query) / qn
        combined += FUNC_BLOCK_WEIGHTS[prefix] * cos
    return -combined


def _quantile_tau_arr(table, method, scores):
    key = f"{method}_quantiles"
    if key not in table:
        raise RuntimeError(f"{key} missing in tau_quantiles; rerun script 06/09")
    q = np.asarray(table[key], dtype=np.float32)  # (n_act, 101)
    s = np.asarray(scores, dtype=np.float32)
    n_q = q.shape[1]
    below = (q < s[:, None]).sum(axis=1)
    k = np.clip(below, 1, n_q - 1)
    lo = np.take_along_axis(q, (k - 1)[:, None], axis=1)[:, 0]
    hi = np.take_along_axis(q, k[:, None], axis=1)[:, 0]
    span = hi - lo
    frac = np.where(span > 0, (s - lo) / np.maximum(span, 1e-12), 0.0)
    frac = np.clip(frac, 0.0, 1.0)
    pct = np.where(s <= q[:, 0], 0.0, np.where(s >= q[:, -1], 1.0,
                     ((k - 1) + frac) / (n_q - 1)))
    return ((2.0 * pct - 1.0) * 100.0).astype(np.float32)


def _quantile_tau(store, method, scores, context):
    if store.is_lite:
        if context == "kprl":
            tau_pan = _quantile_tau_arr(store.tau_tables_for("pan"), method, scores)
            idx_d = store.lite_active_idx("kprl_delta")
            tau_d = _quantile_tau_arr(store.tau_tables_for("kprl_delta"), method, scores[idx_d])
            out = tau_pan.copy()
            out[idx_d] = tau_d
            return out
        idx_a = store.lite_active_idx(context)
        out = np.full(len(store.cp_index), -100.0, dtype=np.float32)
        out[idx_a] = _quantile_tau_arr(store.tau_tables_for(context), method, scores[idx_a])
        return out
    table = store.tau_tables_for(context)
    return _quantile_tau_arr(table, method, scores)


def _lite_func_scores_ctx(store, ctx_dir_name, up_symbols, down_symbols):
    fblk = store.lite_func_block(ctx_dir_name)
    n_act = len(store.lite_active_idx(ctx_dir_name))
    cols_by_prefix = {}
    for fname, prefix in (("progeny", "pw"), ("collectri", "tf"), ("renal_modules", "mod")):
        cols_by_prefix[prefix] = [f"{prefix}_{c}" for c in fblk[f"{fname}_cols"]]
    queries = _build_func_query_vectors(cols_by_prefix, up_symbols, down_symbols)
    combined = np.zeros(n_act, dtype=np.float32)
    for fname, prefix in (("progeny", "pw"), ("collectri", "tf"), ("renal_modules", "mod")):
        query = queries[prefix]
        qn = np.linalg.norm(query)
        if qn == 0:
            continue
        raw_arr = fblk[f"{fname}_raw"]  # (n_act, n_cols) float16
        norms = fblk[f"{fname}_norm"]   # (n_act,) float32
        dots = np.empty(n_act, dtype=np.float32)
        for start in range(0, n_act, 4096):
            end = min(start + 4096, n_act)
            dots[start:end] = raw_arr[start:end].astype(np.float32) @ query
        cos = dots / (np.maximum(norms, 1e-9) * qn)
        combined += FUNC_BLOCK_WEIGHTS[prefix] * cos
    return -combined


def _score_lite_dir(store, ctx_dir_name, up_cols, dn_cols, up_symbols, dn_symbols,
                    kernels=METHODS, compute_tau=True):
    n_genes = len(store.genes)
    n_act = len(store.lite_active_idx(ctx_dir_name))
    raw = {}
    if "xsum" in kernels:
        acc_up = store.lite_sum_xsum_cols(ctx_dir_name, up_cols)
        acc_dn = store.lite_sum_xsum_cols(ctx_dir_name, dn_cols)
        denom = max(len(up_cols) + len(dn_cols), 1)
        raw["xsum"] = -(acc_up - acc_dn) / denom
    if "zhang" in kernels:
        z_up = store.lite_read_zhang_cols(ctx_dir_name, up_cols).astype(np.int32).sum(axis=1) / 127.0
        z_dn = store.lite_read_zhang_cols(ctx_dir_name, dn_cols).astype(np.int32).sum(axis=1) / 127.0
        denom = max(len(up_cols) + len(dn_cols), 1)
        raw["zhang"] = ((-z_up + z_dn) / denom).astype(np.float32)
    if "wtcs" in kernels:
        r_up = store.lite_read_ranks_cols(ctx_dir_name, up_cols)
        r_dn = store.lite_read_ranks_cols(ctx_dir_name, dn_cols)
        es_up = signed_es_sub(r_up, n_genes)
        es_dn = signed_es_sub(r_dn, n_genes)
        raw["wtcs"] = np.where(np.sign(es_up) * np.sign(es_dn) < 0,
                               -(es_up - es_dn) / 2.0, 0.0).astype(np.float32)
    if "func" in kernels:
        raw["func"] = _lite_func_scores_ctx(store, ctx_dir_name, up_symbols, dn_symbols)

    tau = {}
    if compute_tau:
        table = store.tau_tables_for(ctx_dir_name)
        for m in kernels:
            tau[m] = _quantile_tau_arr(table, m, raw[m])
    return raw, tau, n_act


def _score_single_context_lite(store, up_cols, dn_cols, up_symbols, dn_symbols,
                               context, kernels=METHODS, compute_tau=True,
                               n_genes_override=None):
    n_cp = len(store.cp_index)
    if context == "kprl":
        raw, tau, _ = _score_lite_dir(
            store, "pan", up_cols, dn_cols, up_symbols, dn_symbols, kernels, compute_tau
        )
        raw_d, tau_d, _ = _score_lite_dir(
            store, "kprl_delta", up_cols, dn_cols, up_symbols, dn_symbols, kernels, compute_tau
        )
        idx_d = store.lite_active_idx("kprl_delta")
        for m in kernels:
            raw[m][idx_d] = raw_d[m]
            if compute_tau:
                tau[m][idx_d] = tau_d[m]
        return raw, tau

    raw_a, tau_a, _ = _score_lite_dir(
        store, context, up_cols, dn_cols, up_symbols, dn_symbols, kernels, compute_tau
    )
    if context == "pan":
        return raw_a, tau_a
    idx_a = store.lite_active_idx(context)
    raw, tau = {}, {}
    for m in kernels:
        r_full = np.zeros(n_cp, dtype=np.float32)
        r_full[idx_a] = raw_a[m]
        raw[m] = r_full
        if compute_tau:
            t_full = np.full(n_cp, -100.0, dtype=np.float32)
            t_full[idx_a] = tau_a[m]
            tau[m] = t_full
    return raw, tau


def _resolve(store, up, down, gene_tier):
    up_cols, up_missing = store.resolve_genes(up)
    dn_cols, dn_missing = store.resolve_genes(down)
    if gene_tier in ("lm", "bing"):
        flag = store.genes["is_landmark"] if gene_tier == "lm" else store.genes["is_bing"]
        allowed = set(store.genes.loc[flag == 1, "matrix_col_idx"])
        up_cols = [c for c in up_cols if c in allowed]
        dn_cols = [c for c in dn_cols if c in allowed]
    overlap = set(up_cols) & set(dn_cols)
    if overlap:
        dn_cols = [c for c in dn_cols if c not in overlap]
    if not up_cols or not dn_cols:
        raise ValueError("signature needs at least one up and one down gene")
    return up_cols, dn_cols, up_missing, dn_missing


def _signature_scores(store, up_cols, dn_cols, context, disease=None, compartment=None):
    up_symbols = store.genes.iloc[up_cols]["symbol"].tolist()
    dn_symbols = store.genes.iloc[dn_cols]["symbol"].tolist()
    contexts = (_time01_contexts(disease, compartment)
                if context == "auto" else [context])
    weights = _method_weights()
    raw_acc = {m: None for m in METHODS}
    tau_acc = {m: None for m in METHODS}
    conn_acc = None
    for ctx in contexts:
        if store.is_lite:
            raw, tau = _score_single_context_lite(
                store, up_cols, dn_cols, up_symbols, dn_symbols, ctx,
                kernels=METHODS, compute_tau=True
            )
        else:
            raw = {
                "xsum": xsum_extreme(store, ctx, up_cols, dn_cols).astype(np.float32),
                "zhang": zhang_score(store, ctx, up_cols, dn_cols).astype(np.float32),
                "wtcs": wtcs_score(store, ctx, up_cols, dn_cols).astype(np.float32),
                "func": func_scores(store, up_symbols, dn_symbols, ctx),
            }
            tau = {m: _quantile_tau(store, m, raw[m], ctx) for m in METHODS}
        conn = sum(weights[m] * tau[m] for m in METHODS) / len(contexts)
        for m in METHODS:
            raw_acc[m] = raw[m] if raw_acc[m] is None else raw_acc[m] + raw[m]
            tau_acc[m] = tau[m] if tau_acc[m] is None else tau_acc[m] + tau[m]
        conn_acc = conn if conn_acc is None else conn_acc + conn
    raw = {m: raw_acc[m] / len(contexts) for m in METHODS}
    tau = {m: tau_acc[m] / len(contexts) for m in METHODS}
    return raw, tau, conn_acc


def rank_all(up, down, context="kprl", gene_tier="all", disease=None,
             compartment=None):
    """Unfiltered library ranking (no safety rerank)."""
    store = get_store()
    up_cols, dn_cols, _, _ = _resolve(store, up, down, gene_tier)
    raw, tau, renalconn = _signature_scores(store, up_cols, dn_cols, context,
                                            disease, compartment)
    out = {"pert_id": store.cp_index["pert_id"].to_numpy(), "renalconn": renalconn}
    for m in METHODS:
        out[f"score_{m}"] = raw[m]
        out[f"tau_{m}"] = tau[m]
    return pd.DataFrame(out)


def _compartment_support(store, compartment):
    table = store.expr_kidney_cp
    key = COMPARTMENT_COLUMNS.get((compartment or "whole_kidney").lower(), "whole_kidney")
    if key not in table.columns:
        return pd.Series(0.0, index=table.index)
    return table[key].reindex(store.cp_index["pert_id"]).fillna(0.0)


def score_signature(up, down, context="kprl", gene_tier="all", compartment=None,
                    weights=None, filters=None, top_k=50, disease=None):
    store = get_store()
    weights = weights or {}
    filters = filters or {}
    up_cols, dn_cols, up_missing, dn_missing = _resolve(store, up, down, gene_tier)
    raw, tau, renalconn = _signature_scores(store, up_cols, dn_cols, context,
                                            disease, compartment)

    result = store.cp_index[["pert_id", "pert_iname", "matrix_row_idx",
                             "n_sigs", "kprl_lambda"]].copy()
    result["renalconn"] = renalconn
    for m in METHODS:
        result[f"score_{m}"] = raw[m]
        result[f"tau_{m}"] = tau[m]
    result = result.merge(
        store.compounds.reset_index(drop=True)[
            ["pert_id", "inchikey14", "clinical_phase", "moa",
             "diril_label", "tdiki_prob", "tdiki_tier"]],
        on="pert_id", how="left")

    w1 = float(weights.get("w1", 1.0))
    w2 = float(weights.get("w2", 0.5))
    w3 = float(weights.get("w3", 0.2))
    w4 = float(weights.get("w4", 0.2))
    risk = result["tdiki_prob"].fillna(0.5).to_numpy(dtype=np.float32) * 100
    expr = _compartment_support(store, compartment).to_numpy(dtype=np.float32)
    mimic = store.genetic_mimicry_cp["mimicry_max"].reindex(
        store.cp_index["pert_id"]).fillna(0.0).to_numpy(dtype=np.float32)
    result["expr_kidney"] = expr
    result["mimicry"] = mimic
    result["rtps"] = (w1 * result["renalconn"] - w2 * risk
                      + w3 * expr * 100 + w4 * mimic * 100)

    if filters.get("approved_only"):
        phase = result["clinical_phase"].fillna("").str.lower()
        result = result[phase.str.contains("approved|launched")]
    if filters.get("max_diki_tier"):
        allowed = {"Low"} if filters["max_diki_tier"] == "Low" else {"Low", "Moderate"}
        result = result[result["tdiki_tier"].isin(allowed) | result["tdiki_tier"].isna()]
    if filters.get("clinical_override"):
        result = result[~(result["diril_label"] == 1)]

    result = result.sort_values("rtps", ascending=False).head(top_k)
    if filters.get("collapse_scaffold"):
        result = result.drop_duplicates("inchikey14")
    records = json.loads(result.to_json(orient="records"))

    provenance = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": ENGINE_VERSION,
        "store_mode": "lite" if store.is_lite else "full",
        "context": context,
        "gene_tier": gene_tier,
        "compartment": compartment,
        "weights": {"w1": w1, "w2": w2, "w3": w3, "w4": w4,
                    "methods": _method_weights()},
        "filters": filters,
        "input_hash": hashlib.sha256(json.dumps(
            {"up": sorted(up), "down": sorted(down)}, sort_keys=True).encode()).hexdigest(),
        "matrix_version": "kprl-2026.11-modz",
        "tau": "empirical signed percentile, 600-signature background",
        "n_up": len(up_cols), "n_down": len(dn_cols),
        "missing_up": up_missing[:50], "missing_down": dn_missing[:50],
    }
    return {"results": records, "provenance": provenance}


def _lite_pathway_tf_matrix(store, targets: dict, context: str):
    """Extract only requested target columns in Lite mode without duplicating full tables."""
    n_cp = len(store.cp_index)
    if context == "kprl":
        base = store.lite_func_block("pan")
        delta = store.lite_func_block("kprl_delta")
        idx_d = store.lite_active_idx("kprl_delta")
    else:
        base = store.lite_func_block(context)
        idx_a = store.lite_active_idx(context) if context != "pan" else None
        delta = None

    col_lookup = {}
    for fname, prefix in (("progeny", "pw"), ("collectri", "tf"), ("renal_modules", "mod")):
        cols = [str(c) for c in base[f"{fname}_cols"]]
        for j, raw_name in enumerate(cols):
            full_name = f"{prefix}_{raw_name}"
            col_lookup[full_name] = (fname, j)
            col_lookup.setdefault(raw_name.upper(), []).append((full_name, fname, j))

    available, missing = {}, []
    vecs = []
    for key, direction in targets.items():
        hit = None
        if key in col_lookup and isinstance(col_lookup[key], tuple):
            fname, j = col_lookup[key]
            hit = (key, fname, j)
        else:
            matches = col_lookup.get(key.upper())
            if isinstance(matches, list) and matches:
                hit = matches[0]
        if not hit:
            missing.append(key)
            continue
        full_name, fname, j = hit
        available[full_name] = float(direction)
        if context == "kprl":
            v = base[f"{fname}_raw"][:, j].astype(np.float32)
            v[idx_d] = delta[f"{fname}_raw"][:, j].astype(np.float32)
        elif context == "pan":
            v = base[f"{fname}_raw"][:, j].astype(np.float32)
        else:
            v = np.zeros(n_cp, dtype=np.float32)
            v[idx_a] = base[f"{fname}_raw"][:, j].astype(np.float32)
        vecs.append(v)

    if not available:
        raise ValueError(f"no known pathway/TF in {list(targets)}")
    sub = np.column_stack(vecs).astype(np.float32)
    return sub, available, missing


def score_pathway_tf(targets: dict, top_k=20, context="kprl"):
    store = get_store()
    if store.is_lite:
        sub, available, missing = _lite_pathway_tf_matrix(store, targets, context)
    else:
        blocks = [store.func_matrix(name, context).reindex(store.cp_index["pert_id"])
                  for name in ("progeny", "collectri", "renal_modules")]
        acts = pd.concat(blocks, axis=1)
        available, missing = {}, []
        for key, direction in targets.items():
            if key in acts.columns:
                available[key] = float(direction)
            else:
                matches = [c for c in acts.columns if c.split("_", 1)[1].upper() == key.upper()]
                if matches:
                    available[matches[0]] = float(direction)
                else:
                    missing.append(key)
        if not available:
            raise ValueError(f"no known pathway/TF in {list(targets)}")
        sub = acts[list(available)].fillna(0.0).to_numpy(dtype=np.float32)

    std = sub.std(axis=0) + 1e-6
    z = sub / std
    direction = np.array([available[c] for c in available], dtype=np.float32)
    score = (z * direction).mean(axis=1)
    out = store.cp_index[["pert_id", "pert_iname"]].copy()
    out["pathway_tf_score"] = score
    out = out.merge(store.compounds.reset_index(drop=True)[
        ["pert_id", "clinical_phase", "tdiki_prob", "tdiki_tier", "diril_label"]],
        on="pert_id", how="left")
    out = out.sort_values("pathway_tf_score", ascending=False).head(top_k)
    return {"results": json.loads(out.to_json(orient="records")),
            "used": list(available), "missing": missing}
