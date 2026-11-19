"""Deterministic scoring engine: WTCS / XSum / ZhangScore / functional
projection / renal tau calibration / NephroSafe-ReRank (RTPS)."""
import hashlib
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yaml

from ..core.store import CONFIG, get_store

METHODS = ("xsum", "zhang", "wtcs", "func")
SIZE_BINS = (20, 50, 100, 200, 400)
COMPARTMENT_COLUMNS = {
    "podocyte": ["sc_podocyte"],
    "pt": ["sc_pt"],
    "tal": ["sc_tal"],
    "dct": ["sc_dct"],
    "cd": ["sc_cd"],
    "endo": ["sc_endo"],
    "immune": ["sc_immune"],
    "glomerulus": ["sc_podocyte", "sc_endo"],
    "tubule": ["sc_pt", "sc_tal", "sc_dct", "sc_cd"],
    "whole_kidney": ["hpa_kidney_ntpm"],
}


def _ranks_for(store, context):
    if context == "kprl":
        return store.ranks
    path = store.store / "matrices" / f"{context}_cp_ranks.npy"
    if path.exists():
        return np.load(path, mmap_mode="r")
    matrix = store.matrix(context)
    n_drugs, n_genes = matrix.shape
    ranks = np.empty((n_drugs, n_genes), dtype=np.int16)
    positions = np.arange(n_genes, dtype=np.int16)[None, :]
    for start in range(0, n_drugs, 1000):
        block = np.asarray(matrix[start:start + 1000])
        idx = np.argsort(-block, axis=1)
        np.put_along_axis(ranks[start:start + 1000], idx, positions, axis=1)
    np.save(path, ranks)
    return np.load(path, mmap_mode="r")


def signed_es(ranks, idx, n_genes):
    pos = np.sort(np.asarray(ranks[:, idx]), axis=1).astype(np.float32)
    k = pos.shape[1]
    j = np.arange(k, dtype=np.float32)[None, :]
    misses = pos - j
    after = (j + 1) / k - misses / (n_genes - k)
    before = j / k - misses / (n_genes - k)
    hi = np.maximum(after.max(axis=1), 0.0)
    lo = np.minimum(before.min(axis=1), 0.0)
    return np.where(np.abs(hi) >= np.abs(lo), hi, lo)


def _size_bin(n):
    return min(SIZE_BINS, key=lambda b: abs(b - n))


def _tau(store, method, score, n_genes_in):
    if method == "func":
        pct = pd.Series(score).rank(pct=True).to_numpy()
        return -(2 * pct - 1) * 100
    table = store.tau_tables
    size = _size_bin(n_genes_in)
    mean = table[f"{method}_mean_{size}"]
    std = table[f"{method}_std_{size}"]
    z = (score - mean) / (std + 1e-6)
    return -100.0 * np.tanh(z / 3.0)


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


def func_scores(store, up_symbols, down_symbols):
    """Project the disease signature into pathway/TF/module space and compare
    with each compound's precomputed activity profile."""
    global _NET_CACHE, _ACT_CACHE
    if not _NET_CACHE:
        _NET_CACHE = _load_networks()
    if "acts" not in _ACT_CACHE:
        blocks = []
        for name, prefix in (("progeny", "pw"), ("collectri", "tf"), ("renal_modules", "mod")):
            frame = store.func_matrix(name)
            blocks.append(frame)
        acts = pd.concat(blocks, axis=1)
        acts = acts.reindex(store.cp_index["pert_id"]).fillna(0.0)
        _ACT_CACHE["acts"] = (acts.columns.tolist(),
                              acts.to_numpy(dtype=np.float32))
    columns, drug_acts = _ACT_CACHE["acts"]

    up = set(s.upper() for s in up_symbols)
    down = set(s.upper() for s in down_symbols)
    vector = np.zeros(len(columns), dtype=np.float32)
    for prefix, net in _NET_CACHE.items():
        net = net.copy()
        net["target"] = net["target"].str.upper()
        for source, sub in net.groupby("source"):
            col = f"{prefix}_{source}"
            if col not in columns:
                continue
            weight = dict(zip(sub["target"], sub["weight"]))
            pos = sum(weight.get(g, 0.0) for g in up)
            neg = sum(weight.get(g, 0.0) for g in down)
            denom = sum(abs(weight.get(g, 0.0)) for g in up | down) or 1.0
            vector[columns.index(col)] = (pos - neg) / denom
    norm = np.linalg.norm(vector)
    if norm == 0:
        return np.zeros(len(drug_acts), dtype=np.float32)
    drug_norm = np.linalg.norm(drug_acts, axis=1) + 1e-6
    cosine = (drug_acts @ vector) / (drug_norm * norm)
    return -cosine


def _expression_score(store, pert_ids, compartment):
    cols = COMPARTMENT_COLUMNS.get((compartment or "whole_kidney").lower(),
                                   COMPARTMENT_COLUMNS["whole_kidney"])
    expr = store.kidney_expression
    available = [c for c in cols if c in expr.columns]
    if not available:
        return {p: 0.0 for p in pert_ids}
    values = np.log1p(expr[available].fillna(0).clip(lower=0)).mean(axis=1)
    values = np.clip(values / np.log1p(1000), 0, 1)
    lookup = values.to_dict()
    targets = _targets_map(store)
    out = {}
    for pid in pert_ids:
        entrez = targets.get(pid, [])
        vals = [lookup.get(str(g)) for g in entrez if str(g) in lookup]
        out[pid] = float(np.mean(vals)) if vals else 0.0
    return out


def _targets_map(store):
    if "targets" not in _ACT_CACHE:
        con = store.db()
        try:
            frame = pd.read_sql("SELECT pert_id, entrez_id FROM drug_targets "
                                "WHERE entrez_id IS NOT NULL", con)
        finally:
            con.close()
        mapping = {}
        for pid, group in frame.groupby("pert_id"):
            mapping[pid] = list(group["entrez_id"].astype(str))
        _ACT_CACHE["targets"] = mapping
    return _ACT_CACHE["targets"]


def _mimicry(store, rows):
    from scipy.stats import pearsonr
    genetic = store.genetic_index_map()
    target_symbols = genetic["pert_iname"].fillna("").str.upper()
    by_symbol = {}
    for idx, sym in enumerate(target_symbols):
        by_symbol.setdefault(sym, []).append(idx)
    matrix = store.matrix("kprl")
    gen_mat = np.load(store.store / "matrices" / "genetic_consensus.npy", mmap_mode="r")
    targets = _targets_map(store)
    entrez_to_symbol = dict(zip(store.genes["entrez_id"], store.genes["symbol"].str.upper()))
    row_lookup = dict(zip(store.cp_index["pert_id"], store.cp_index["matrix_row_idx"]))
    out = {}
    for pid in rows:
        entrez = targets.get(pid, [])
        if not entrez:
            out[pid] = 0.0
            continue
        symbols = {entrez_to_symbol[e] for e in entrez if e in entrez_to_symbol}
        idx = [i for s in symbols for i in by_symbol.get(s, [])][:8]
        if not idx:
            out[pid] = 0.0
            continue
        row = np.asarray(matrix[int(row_lookup[pid])])
        cors = []
        for i in idx:
            g = np.asarray(gen_mat[i])
            if g.std() > 0 and row.std() > 0:
                cors.append(float(np.corrcoef(row, g)[0, 1]))
        out[pid] = max(cors) if cors else 0.0
    return out


def rank_all(up, down, context="kprl", gene_tier="all"):
    """Unfiltered RenalConn ranking over the whole library (no safety rerank)."""
    store = get_store()
    up_cols, up_missing = store.resolve_genes(up)
    dn_cols, dn_missing = store.resolve_genes(down)
    if gene_tier in ("lm", "bing"):
        flag = store.genes["is_landmark"] if gene_tier == "lm" else store.genes["is_bing"]
        allowed = set(store.genes.loc[flag == 1, "matrix_col_idx"])
        up_cols = [c for c in up_cols if c in allowed]
        dn_cols = [c for c in dn_cols if c in allowed]
    if not up_cols or not dn_cols:
        raise ValueError("signature needs at least one up and one down gene")

    matrix = store.matrix(context)
    n_genes = matrix.shape[1]
    xsum = (np.asarray(matrix[:, up_cols]).mean(axis=1)
            - np.asarray(matrix[:, dn_cols]).mean(axis=1))
    ranks = _ranks_for(store, context)
    up_rank = (n_genes - np.asarray(ranks[:, up_cols], dtype=np.float32)).mean(axis=1) / n_genes
    dn_rank = (n_genes - np.asarray(ranks[:, dn_cols], dtype=np.float32)).mean(axis=1) / n_genes
    zhang = up_rank - dn_rank
    es_up = signed_es(ranks, up_cols, n_genes)
    es_dn = signed_es(ranks, dn_cols, n_genes)
    wtcs = np.where(np.sign(es_up) * np.sign(es_dn) < 0, -(es_up - es_dn) / 2.0, 0.0)
    up_symbols = store.genes.iloc[up_cols]["symbol"].tolist()
    dn_symbols = store.genes.iloc[dn_cols]["symbol"].tolist()
    func = func_scores(store, up_symbols, dn_symbols)

    n_in = max(len(up_cols), len(dn_cols))
    raw = {"xsum": xsum, "zhang": zhang, "wtcs": wtcs, "func": func}
    tau = {m: _tau(store, m, raw[m], n_in) for m in METHODS}
    renalconn = sum(0.25 * (-tau[m]) for m in METHODS)
    return pd.DataFrame({"pert_id": store.cp_index["pert_id"].to_numpy(),
                         "renalconn": renalconn,
                         "tau_xsum": tau["xsum"], "tau_zhang": tau["zhang"],
                         "tau_wtcs": tau["wtcs"], "tau_func": tau["func"]})


def score_signature(up, down, context="kprl", gene_tier="all", compartment=None,
                    weights=None, filters=None, top_k=50):
    store = get_store()
    weights = weights or {}
    filters = filters or {}
    up_cols, up_missing = store.resolve_genes(up)
    dn_cols, dn_missing = store.resolve_genes(down)
    if not up_cols and not dn_cols:
        raise ValueError("no resolvable genes in the input signature")

    if gene_tier in ("lm", "bing"):
        flag = store.genes["is_landmark"] if gene_tier == "lm" else store.genes["is_bing"]
        allowed = set(store.genes.loc[flag == 1, "matrix_col_idx"])
        up_cols = [c for c in up_cols if c in allowed]
        dn_cols = [c for c in dn_cols if c in allowed]
    if not up_cols or not dn_cols:
        raise ValueError("signature needs at least one up and one down gene")

    matrix = store.matrix(context)
    n_genes = matrix.shape[1]
    xsum = (np.asarray(matrix[:, up_cols]).mean(axis=1)
            - np.asarray(matrix[:, dn_cols]).mean(axis=1))
    ranks = _ranks_for(store, context)
    up_rank = (n_genes - np.asarray(ranks[:, up_cols], dtype=np.float32)).mean(axis=1) / n_genes
    dn_rank = (n_genes - np.asarray(ranks[:, dn_cols], dtype=np.float32)).mean(axis=1) / n_genes
    zhang = up_rank - dn_rank
    es_up = signed_es(ranks, up_cols, n_genes)
    es_dn = signed_es(ranks, dn_cols, n_genes)
    wtcs = np.where(np.sign(es_up) * np.sign(es_dn) < 0, -(es_up - es_dn) / 2.0, 0.0)

    up_symbols = store.genes.iloc[up_cols]["symbol"].tolist()
    dn_symbols = store.genes.iloc[dn_cols]["symbol"].tolist()
    func = func_scores(store, up_symbols, dn_symbols)

    n_in = max(len(up_cols), len(dn_cols))
    raw = {"xsum": xsum, "zhang": zhang, "wtcs": wtcs, "func": func}
    tau = {m: _tau(store, m, raw[m], n_in) for m in METHODS}
    alphas = weights.get("methods", {m: 0.25 for m in METHODS})
    renalconn = sum(alphas.get(m, 0.25) * (-tau[m]) for m in METHODS)

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
    risk = result["tdiki_prob"].fillna(0.5).to_numpy() * 100
    result["rtps"] = w1 * result["renalconn"] - w2 * risk

    if filters.get("approved_only"):
        phase = result["clinical_phase"].fillna("").str.lower()
        result = result[phase.str.contains("approved|launched")]
    if filters.get("max_diki_tier"):
        allowed = {"Low"} if filters["max_diki_tier"] == "Low" else {"Low", "Moderate"}
        result = result[result["tdiki_tier"].isin(allowed) | result["tdiki_tier"].isna()]

    result = result.sort_values("rtps", ascending=False)
    top = result.head(max(top_k * 3, 60)).copy()

    expr = _expression_score(store, top["pert_id"].tolist(), compartment)
    mimicry = _mimicry(store, top["pert_id"].tolist())
    top["expr_kidney"] = top["pert_id"].map(expr).fillna(0.0)
    top["mimicry"] = top["pert_id"].map(mimicry).fillna(0.0)
    top["rtps"] = (top["rtps"] + w3 * top["expr_kidney"] * 100
                   + w4 * top["mimicry"] * 100)

    if filters.get("collapse_scaffold"):
        top = top.sort_values("rtps", ascending=False).drop_duplicates("inchikey14")

    top = top.sort_values("rtps", ascending=False).head(top_k)
    records = json.loads(top.to_json(orient="records"))

    provenance = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "context": context,
        "gene_tier": gene_tier,
        "compartment": compartment,
        "weights": {"w1": w1, "w2": w2, "w3": w3, "w4": w4,
                    "methods": alphas},
        "filters": filters,
        "input_hash": hashlib.sha256(json.dumps(
            {"up": sorted(up), "down": sorted(down)}, sort_keys=True).encode()).hexdigest(),
        "matrix_version": "kprl-2026.11",
        "n_up": len(up_cols), "n_down": len(dn_cols),
        "missing_up": up_missing[:50], "missing_down": dn_missing[:50],
    }
    return {"results": records, "provenance": provenance}


def score_pathway_tf(targets: dict, top_k=20):
    store = get_store()
    blocks = []
    for name in ("progeny", "collectri", "renal_modules"):
        frame = store.func_matrix(name)
        blocks.append(frame)
    acts = pd.concat(blocks, axis=1).reindex(store.cp_index["pert_id"])
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
