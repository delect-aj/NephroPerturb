#!/usr/bin/env python
"""BM-1 (v2): MoA retrieval with fair same-pool comparison and kernel ablation.

Pool A (renal-overlap, N=6,163, all variants evaluated on the SAME 300
queries): pan_mean (legacy arithmetic mean), pan_modz, renal_epi_modz,
kprl_k<K> (kappa scan), kprl_tier (Landmark/BING tier weights).

Pool B (full library, N=21,299, SAME 300 queries): profile similarity
(pan_modz vs kprl_modz) plus signature-kernel retrieval (wtcs, true_xsum,
true_zhang, fixed_func, real_tau_ensemble); each query signature is the
query compound's own kprl profile top-150 up / bottom-150 down.

Metrics: AUROC, AUPRC, median percentile rank of first relevant hit
(lower is better), Recall@1/5/10%, MRR; paired two-sided Wilcoxon across
queries between variants.

PRE-REGISTERED selection rule (written into the output):
  kappa        := argmax mean AUROC in Pool A (tie-break: lower median_pct)
  kernel/weights := argmin median_pct in Pool B among {real_tau_ensemble,
                    single best kernel}; a single kernel wins if it strictly
                    beats the equal-weight ensemble (no complexity for show).
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))
from common import paths  # noqa: E402

OUT = ROOT / "benchmarks" / "outputs"
KAPPA_SCAN = (0.5, 1.0, 2.0, 5.0, 10.0, 20.0)
KERNELS = ("wtcs", "xsum", "zhang", "func", "ensemble")
QUERY_UP_DOWN = 150


def l2_normalize(matrix, weights=None):
    block = np.asarray(matrix, dtype=np.float32)
    if weights is not None:
        block = block * weights
    norms = np.linalg.norm(block, axis=1, keepdims=True) + 1e-9
    return block / norms


def merge_truth(compounds, hub):
    compounds = compounds.copy()
    compounds["name_lower"] = compounds["pert_iname"].fillna("").str.lower().str.strip()
    annotated = compounds.merge(hub[["pert_iname_lower", "moa"]],
                                left_on="name_lower", right_on="pert_iname_lower",
                                how="inner")
    annotated = annotated[annotated["moa"].notna() & (annotated["moa"] != "")]
    truth = {}
    for pid, moa in zip(annotated["pert_id"], annotated["moa"]):
        truth[pid] = moa.strip().lower()
    return truth


def eval_ranking(scores, relevant_mask):
    """scores: (n,) higher = better; relevant_mask: bool (n,)."""
    n = len(scores)
    n_rel = int(relevant_mask.sum())
    if n_rel == 0:
        return None
    order = np.argsort(-scores, kind="stable")
    hits = relevant_mask[order]
    first = int(np.argmax(hits)) if hits.any() else n
    y = relevant_mask.astype(int)
    try:
        auroc = float(roc_auc_score(y, scores))
        auprc = float(average_precision_score(y, scores))
    except ValueError:
        auroc = auprc = None
    ranks = np.flatnonzero(hits) + 1
    return {
        "auroc": auroc, "auprc": auprc,
        "first_pct": first / n,
        "mrr": float(np.mean(1.0 / ranks)) if len(ranks) else 0.0,
        "rec@1%": bool(hits[:max(1, int(n * 0.01))].any()),
        "rec@5%": bool(hits[:max(1, int(n * 0.05))].any()),
        "rec@10%": bool(hits[:max(1, int(n * 0.10))].any()),
        "n_relevant": n_rel,
    }


def summarize(per_query, label):
    rows = [r for r in per_query if r]
    out = {"label": label, "n_queries": len(rows)}
    for k in ("auroc", "auprc", "first_pct", "mrr"):
        vals = [r[k] for r in rows if r[k] is not None]
        out[k] = float(np.mean(vals)) if vals else None
    for k in ("rec@1%", "rec@5%", "rec@10%"):
        out[k] = float(np.mean([r[k] for r in rows])) if rows else None
    return out


def profile_variant(matrix, cand_rows, query_rows, truth_by_pid, cand_pids,
                    tier_weights=None, label=""):
    normed = l2_normalize(matrix, tier_weights)
    cand = normed[cand_rows]
    qpos = np.searchsorted(cand_rows, query_rows)
    sims_block = cand @ cand[qpos].T
    per_query = []
    for j, row in enumerate(query_rows):
        pid = cand_pids[row] if cand_pids is not None else None
        moa = truth_by_pid.get(pid)
        if not moa:
            per_query.append(None)
            continue
        rel = np.array([truth_by_pid.get(p) == moa for p in cand_pids[cand_rows]])
        sims = sims_block[:, j].copy()
        sims[cand_rows == row] = -1e9
        rel[cand_rows == row] = False
        per_query.append(eval_ranking(sims, rel))
    return summarize(per_query, label), per_query


def kernel_variant(store, scoring, query_rows, matrix_ctx, truth_by_pid,
                   matrix, kernel, cp_pids, label=""):
    from app.engine import scoring as sc
    per_query = []
    kprl = store.matrix(matrix_ctx)
    for row in query_rows:
        pid = cp_pids[row]
        moa = truth_by_pid.get(pid)
        if not moa:
            per_query.append(None)
            continue
        z = np.asarray(kprl[row], dtype=np.float32)
        order = np.argsort(-z)
        up = order[:QUERY_UP_DOWN]
        dn = order[::-1][:QUERY_UP_DOWN]
        if kernel == "wtcs":
            s = sc.wtcs_score(store, matrix_ctx, list(up), list(dn))
        elif kernel == "xsum":
            s = sc.xsum_extreme(store, matrix_ctx, list(up), list(dn))
        elif kernel == "zhang":
            s = sc.zhang_score(store, matrix_ctx, list(up), list(dn))
        elif kernel == "func":
            up_sym = store.genes.iloc[up]["symbol"].tolist()
            dn_sym = store.genes.iloc[dn]["symbol"].tolist()
            s = sc.func_scores(store, up_sym, dn_sym, matrix_ctx)
        else:  # ensemble
            up_sym = store.genes.iloc[up]["symbol"].tolist()
            dn_sym = store.genes.iloc[dn]["symbol"].tolist()
            raw = {
                "xsum": sc.xsum_extreme(store, matrix_ctx, list(up), list(dn)),
                "zhang": sc.zhang_score(store, matrix_ctx, list(up), list(dn)),
                "wtcs": sc.wtcs_score(store, matrix_ctx, list(up), list(dn)),
                "func": sc.func_scores(store, up_sym, dn_sym, matrix_ctx),
            }
            tau = {m: sc._quantile_tau(store, m, raw[m], matrix_ctx) for m in sc.METHODS}
            w = sc._method_weights()
            s = sum(w[m] * tau[m] for m in sc.METHODS)
        s = np.asarray(s, dtype=np.float64).copy()
        s[row] = -1e9
        rel = np.array([truth_by_pid.get(p) == moa for p in cp_pids])
        rel[row] = False
        per_query.append(eval_ranking(s, rel))
    return summarize(per_query, label), per_query


def main():
    import argparse
    from app.core.store import MatrixStore
    from app.engine import scoring
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool-a-only", action="store_true",
                    help="run only the kappa scan (no tau-dependent Pool B)")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    store_path = paths()["store"]
    compounds = pd.read_parquet(store_path / "chem" / "compounds.parquet")
    cp_index = pd.read_parquet(store_path / "cp_index.parquet")
    hub = pd.read_parquet(store_path / "annotations" / "repurposing_hub.parquet")
    genes = pd.read_parquet(store_path / "genes" / "gene_universe.parquet")
    cp_pids = cp_index["pert_id"].to_numpy()
    truth = merge_truth(compounds, hub)
    print(f"[bm1] compounds with MoA: {len(truth)}")

    pid_to_row = {p: int(r) for p, r in zip(cp_index["pert_id"], cp_index["matrix_row_idx"])}
    truth_rows = np.array(sorted(pid_to_row[p] for p in truth if p in pid_to_row))
    renal_rows = np.flatnonzero(cp_index["n_renal_sigs"].to_numpy() > 0)
    renal_set = set(renal_rows.tolist())

    rng = np.random.default_rng(20261119)
    pool_a_rows = np.array([r for r in truth_rows if int(r) in renal_set])
    queries_a = np.sort(rng.choice(pool_a_rows, size=min(300, len(pool_a_rows)),
                                   replace=False))
    non_renal = np.array([r for r in truth_rows if int(r) not in renal_set])
    queries_b = np.sort(rng.choice(non_renal if len(non_renal) >= 300 else truth_rows,
                                   size=min(300, len(truth_rows)), replace=False))
    print(f"[bm1] Pool A queries={len(queries_a)} Pool B queries={len(queries_b)}")

    store = MatrixStore()
    tier_w = np.where(genes["is_landmark"] == 1, 1.0,
                      np.where(genes["is_bing"] == 1, 0.5, 0.25)).astype(np.float32)

    results = {}
    per_query_store = {}
    pa_pids = cp_pids

    def run_matrix(matrix_file, label, cand_rows, queries, tier=None):
        matrix = np.load(store_path / "matrices" / matrix_file, mmap_mode="r")
        sub = {p: truth[p] for p in truth}
        summary, pq = profile_variant(matrix, cand_rows, queries, sub, pa_pids,
                                      tier_weights=tier, label=label)
        results[label] = summary
        per_query_store[label] = pq
        print(f"[bm1] {label}: auroc={summary['auroc']:.3f} "
              f"median_pct={summary['first_pct']:.3f}")

    run_matrix("pan_cp_amean.npy", "pan_mean", renal_rows, queries_a)
    run_matrix("pan_cp_zscore.npy", "pan_modz", renal_rows, queries_a)
    run_matrix("renal_epi_cp_zscore.npy", "renal_epi_modz", renal_rows, queries_a)
    for k in KAPPA_SCAN:
        run_matrix(f"scan/kprl_k{k:g}.npy", f"kprl_k{k:g}", renal_rows, queries_a)
    run_matrix("kprl_cp_zscore.npy", "kprl_tier", renal_rows, queries_a, tier=tier_w)

    def auroc_key(label):
        v = results[label]["auroc"]
        return (v if v is not None else -1.0, -results[label]["first_pct"])

    kappa_labels = [f"kprl_k{k:g}" for k in KAPPA_SCAN]
    best_k = max(kappa_labels, key=auroc_key)
    locked_kappa = float(best_k.split("_k")[1])
    print(f"[bm1] locked kappa={locked_kappa}")

    if args.pool_a_only:
        print(f"[bm1] pool A only, locked kappa={locked_kappa}")
        (OUT / "bm1_moa_retrieval.json").write_text(json.dumps({
            "design": {"mode": "pool_a_only"},
            "metrics": results, "locked_kappa": locked_kappa}, indent=2))
        return

    # Pool B: full library
    all_rows = np.arange(len(cp_index))
    run_matrix("pan_cp_zscore.npy", "B_pan_modz", all_rows, queries_b)
    run_matrix("kprl_cp_zscore.npy", "B_kprl_modz", all_rows, queries_b)
    for kernel in KERNELS:
        summary, pq = kernel_variant(store, scoring, queries_b, "kprl", truth,
                                     None, kernel, cp_pids, label=f"B_{kernel}")
        results[f"B_{kernel}"] = summary
        per_query_store[f"B_{kernel}"] = pq
        print(f"[bm1] B_{kernel}: median_pct={summary['first_pct']:.3f} "
              f"auroc={summary['auroc']:.3f}")

    # Paired Wilcoxon across queries (first-hit percentile; NaN-safe pairing)
    pairs = [("kprl_k0.5", "pan_modz"), ("kprl_k2", "pan_modz"),
             (f"{best_k}", "pan_modz"), (f"{best_k}", "pan_mean"),
             ("kprl_tier", "pan_modz"), ("kprl_tier", "pan_mean"),
             ("kprl_tier", f"{best_k}"), ("pan_modz", "pan_mean"),
             ("B_kprl_modz", "B_pan_modz"), ("B_ensemble", "B_wtcs"),
             ("B_ensemble", "B_func"), ("B_ensemble", "B_xsum"),
             ("B_ensemble", "B_zhang")]
    wilcox = {}
    for a, b in pairs:
        pa, pb = per_query_store.get(a), per_query_store.get(b)
        if not pa or not pb:
            continue
        xs, ys = [], []
        for ra, rb in zip(pa, pb):
            if ra and rb and ra["first_pct"] is not None and rb["first_pct"] is not None:
                xs.append(ra["first_pct"])
                ys.append(rb["first_pct"])
        if len(xs) >= 5:
            try:
                _, p = wilcoxon(xs, ys)
                wilcox[f"wilcoxon_p_{a}_vs_{b}_first_pct"] = float(p)
            except ValueError:
                wilcox[f"wilcoxon_p_{a}_vs_{b}_first_pct"] = None

    # Pre-registered kernel/weight decision
    kernel_labels = {label: results[label]["first_pct"] for label in
                     ("B_wtcs", "B_xsum", "B_zhang", "B_func", "B_ensemble")}
    best_kernel = min(kernel_labels, key=lambda k: kernel_labels[k])
    ensemble_pct = results["B_ensemble"]["first_pct"]
    if best_kernel != "B_ensemble" and kernel_labels[best_kernel] < ensemble_pct - 1e-6:
        decision = {"deploy": best_kernel.replace("B_", ""), "reason":
                    "single kernel strictly beats the equal-weight ensemble"}
    else:
        decision = {"deploy": "ensemble", "reason":
                    "ensemble is not beaten by any single kernel"}

    payload = {
        "design": {
            "pool_a": {"candidates": int(len(renal_rows)),
                       "queries": int(len(queries_a)),
                       "variants": ["pan_mean", "pan_modz", "renal_epi_modz"] + kappa_labels
                                   + ["kprl_tier"]},
            "pool_b": {"candidates": int(len(all_rows)),
                       "queries": int(len(queries_b)),
                       "variants": ["B_pan_modz", "B_kprl_modz"] + [f"B_{k}" for k in KERNELS]},
            "selection_rule": "kappa=argmax Pool-A mean AUROC (tie-break median_pct); "
                              "kernel=single kernel if strictly better than ensemble "
                              "on Pool-B median_pct, else equal-weight ensemble",
        },
        "metrics": results,
        "wilcoxon": wilcox,
        "locked_kappa": locked_kappa,
        "kernel_decision": decision,
        "locked_weights": scoring._method_weights(),
    }
    (OUT / "bm1_moa_retrieval.json").write_text(json.dumps(payload, indent=2))
    print(f"[bm1] kappa={locked_kappa} kernel={decision}")
    print(f"[bm1] wrote {OUT / 'bm1_moa_retrieval.json'}")


if __name__ == "__main__":
    main()
