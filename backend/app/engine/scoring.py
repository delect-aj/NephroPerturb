"""Deterministic scoring engine (scoring v2).

Direction convention: every raw score is REVERSAL-POSITIVE (a high score means
the compound reverses the disease signature). Calibration is an empirical
signed percentile (tau in [-100, 100]) against a 600-signature real-biology
background library built offline per context.

Kernels
  xsum  : classic truncated extreme-value XSum. Only the compound's top-500
          (resp. bottom-500) genes keep their z-value, everything else is 0;
          score = -(sum(Xext[up]) - sum(Xext[dn])) / (|up| + |dn|).
  zhang : magnitude-ordered Zhang score. Per compound, s[d,g] = sign(z_d,g) *
          (G - rank_abs[d,g] + 1); score = (sum_up(-s) + sum_dn(+s)) / bound,
          bound = (|up|+|dn|) * G, strictly in [-1, 1].
  wtcs  : bidirectional weighted KS enrichment (ES_up*ES_dn < 0 gate).
  func  : pathway/TF/module projection with min_n >= 5 target coverage,
          (pos - neg)/sqrt(sum w_hit^2) scaling, block L2 normalisation and
          0.40 (PROGENy) : 0.30 (CollecTRI) : 0.30 (renal modules) mixture,
          reversal = -cosine.
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


def signed_es(ranks, idx, n_genes):
    pos = np.sort(np.asarray(ranks[:, idx]), axis=1).astype(np.float32)
    k = pos.shape[1]
    j = np.arange(k, dtype=np.float32)[None, :]
    misses_before = pos - j
    rs_after = (j + 1) / k - misses_before / (n_genes - k)
    rs_before = j / k - misses_before / (n_genes - k)
    hi = np.maximum(rs_after.max(axis=1), 0.0)
    lo = np.minimum(rs_before.min(axis=1), 0.0)
    return np.where(np.abs(hi) >= np.abs(lo), hi, lo)


def xsum_extreme(store, context, up_cols, dn_cols, top_n=EXTREME_TOP_N):
    """Truncated extreme-value XSum (reversal-positive).

    X_ext keeps a gene's z-value when it is among the compound's top-N OR
    bottom-N extremes (all other genes are 0). A query gene therefore
    contributes positively when the compound strongly up-regulates it and
    negatively when the compound strongly down-regulates it, in both query
    directions.
    """
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
    """Magnitude-ordered Zhang score (reversal-positive, in [-1, 1])."""
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
    ranks = _ranks_for(store, context)
    n_genes = ranks.shape[1]
    es_up = signed_es(ranks, up_cols, n_genes)
    es_dn = signed_es(ranks, dn_cols, n_genes)
    return np.where(np.sign(es_up) * np.sign(es_dn) < 0, -(es_up - es_dn) / 2.0, 0.0)


def _load_networks():
    nets = {}
    net_dir = get_store().store / "annotations" / "networks"
    for name, prefix in (("progeny", "pw"), ("collectri", "tf")):
        path = net_dir / f"{name}.csv"
        if path.exists():
            frame = pd.read_csv(path)
            nets[prefix] = frame[["source", "target", "weight"]]
    modules = CONFIG / "renal_modules.yaml"
    if modules.exists():
        mod = yaml.safe_load(modules.read_text())["modules"]
        rows = [{"source": k, "target": g, "weight": 1.0}
                for k, genes in mod.items() for g in genes]
        nets["mod"] = pd.DataFrame(rows)
    return nets


_NET_CACHE = {}
_ACT_CACHE = {}


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
    """De-noised pathway/TF/module projection (reversal-positive)."""
    global _NET_CACHE
    if not _NET_CACHE:
        _NET_CACHE = _load_networks()
    up = {str(s).upper() for s in up_symbols}
    down = {str(s).upper() for s in down_symbols}
    blocks = _block_activities(store, context)
    combined = np.zeros(len(store.cp_index), dtype=np.float32)
    for prefix, net in _NET_CACHE.items():
        columns, drug_acts = blocks[prefix]
        net = net.copy()
        net["target"] = net["target"].astype(str).str.upper()
        query = np.zeros(len(columns), dtype=np.float32)
        col_pos = {c: i for i, c in enumerate(columns)}
        for source, sub in net.groupby("source"):
            col = f"{prefix}_{source}"
            if col not in col_pos:
                continue
            w = dict(zip(sub["target"], sub["weight"]))
            up_hits = [(g, w[g]) for g in up if g in w]
            dn_hits = [(g, w[g]) for g in down if g in w]
            n_hits = len(up_hits) + len(dn_hits)
            if n_hits < FUNC_MIN_N:
                continue
            pos = sum(v for _, v in up_hits)
            neg = sum(v for _, v in dn_hits)
            norm = np.sqrt(sum(v * v for _, v in up_hits) + sum(v * v for _, v in dn_hits))
            if norm > 0:
                query[col_pos[col]] = (pos - neg) / norm
        qn = np.linalg.norm(query)
        if qn == 0:
            continue
        cos = (drug_acts @ query) / qn
        combined += FUNC_BLOCK_WEIGHTS[prefix] * cos
    return -combined


def _quantile_tau(store, method, scores, context):
    """Empirical signed percentile against the 600-signature background."""
    table = store.tau_tables_for(context)
    key = f"{method}_quantiles"
    if key not in table.files:
        raise RuntimeError(f"{key} missing in tau_null_tables_{context}.npz; rerun script 06")
    q = table[key]                      # (n_compounds, 101) ascending
    s = np.asarray(scores, dtype=np.float32)
    n_q = q.shape[1]
    below = (q < s[:, None]).sum(axis=1)          # 0..n_q
    k = np.clip(below, 1, n_q - 1)
    lo = np.take_along_axis(q, (k - 1)[:, None], axis=1)[:, 0]
    hi = np.take_along_axis(q, k[:, None], axis=1)[:, 0]
    span = hi - lo
    frac = np.where(span > 0, (s - lo) / np.maximum(span, 1e-12), 0.0)
    frac = np.clip(frac, 0.0, 1.0)
    pct = np.where(s <= q[:, 0], 0.0, np.where(s >= q[:, -1], 1.0,
                     ((k - 1) + frac) / (n_q - 1)))
    return ((2.0 * pct - 1.0) * 100.0).astype(np.float32)


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
        # DIRIL-positive compounds are never allowed into the "safe" shortlist
        result = result[~(result["diril_label"] == 1)]

    result = result.sort_values("rtps", ascending=False).head(top_k)
    if filters.get("collapse_scaffold"):
        result = result.drop_duplicates("inchikey14")
    records = json.loads(result.to_json(orient="records"))

    provenance = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": ENGINE_VERSION,
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


def score_pathway_tf(targets: dict, top_k=20, context="kprl"):
    store = get_store()
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
