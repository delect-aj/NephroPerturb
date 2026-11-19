#!/usr/bin/env python
"""BM-1: MoA retrieval ablation across contexts and gene-tier weighting."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from common import paths  # noqa: E402

OUT = ROOT / "benchmarks" / "outputs"


def l2_normalize(matrix, weights=None):
    block = np.asarray(matrix, dtype=np.float32)
    if weights is not None:
        block = block * weights[None, :]
    norms = np.linalg.norm(block, axis=1, keepdims=True) + 1e-9
    return block / norms


def evaluate(query_rows, candidates, truth, sims):
    recalls = {1: [], 5: [], 10: []}
    ranks = []
    for i, row in enumerate(query_rows):
        order = np.argsort(-sims[i])
        order = order[candidates[order] != row]
        group = truth.get(int(row))
        if not group:
            continue
        hits = np.array([truth.get(int(candidates[j])) == group for j in order])
        first = int(np.argmax(hits)) if hits.any() else len(order)
        ranks.append(first + 1)
        for pct in recalls:
            k = max(1, int(len(candidates) * pct / 100))
            recalls[pct].append(bool(hits[:k].any()))
    return {
        "recall@1%": float(np.mean(recalls[1])),
        "recall@5%": float(np.mean(recalls[5])),
        "recall@10%": float(np.mean(recalls[10])),
        "mrr": float(np.mean([1.0 / r for r in ranks])),
        "median_rank": float(np.median(ranks)),
        "n_queries": len(ranks),
        "n_candidates": int(len(candidates)),
    }


def run_context(matrix, candidates, query_rows, truth, weights=None):
    normed = l2_normalize(matrix, weights)
    cand = normed[candidates]
    sims = cand[np.isin(candidates, query_rows)] @ cand.T
    q = candidates[np.isin(candidates, query_rows)]
    return evaluate(q, candidates, truth, sims)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    store = paths()["store"]
    compounds = pd.read_parquet(store / "chem" / "compounds.parquet")
    cp_index = pd.read_parquet(store / "cp_index.parquet")
    hub = pd.read_parquet(store / "annotations" / "repurposing_hub.parquet")
    compounds["name_lower"] = compounds["pert_iname"].fillna("").str.lower().str.strip()
    annotated = compounds.merge(hub[["pert_iname_lower", "moa"]],
                                left_on="name_lower", right_on="pert_iname_lower",
                                how="inner")
    annotated = annotated[annotated["moa"].notna() & (annotated["moa"] != "")]
    print(f"[bm1] compounds with MoA: {len(annotated)}")

    name_to_row = dict(zip(compounds["pert_id"], np.arange(compounds.shape[0])))
    annotated = annotated[annotated["pert_id"].isin(name_to_row)]
    truth = {int(name_to_row[p]): m.lower()
             for p, m in zip(annotated["pert_id"], annotated["moa"])}
    row_has_renal = cp_index.set_index("pert_id").loc[
        compounds["pert_id"], "n_renal_sigs"].to_numpy() > 0
    all_rows = np.arange(len(compounds))
    renal_rows = all_rows[row_has_renal]

    rng = np.random.default_rng(20261119)
    moa_rows = np.array(sorted(truth))
    queries_all = np.sort(rng.choice(moa_rows, size=min(300, len(moa_rows)), replace=False))
    queries_renal = np.sort(rng.choice(np.intersect1d(moa_rows, renal_rows),
                                       size=min(300, len(np.intersect1d(moa_rows, renal_rows))),
                                       replace=False))

    genes = pd.read_parquet(store / "genes" / "gene_universe.parquet")
    tier_w = np.where(genes["is_landmark"] == 1, 1.0,
                      np.where(genes["is_bing"] == 1, 0.5, 0.25)).astype(np.float32)

    results = {}
    contexts = (("pan", "pan_cp_zscore.npy", all_rows, queries_all),
                ("renal_epi", "renal_epi_cp_zscore.npy", renal_rows, queries_renal),
                ("kprl", "kprl_cp_zscore.npy", renal_rows, queries_renal))
    for context, filename, candidates, queries in contexts:
        matrix = np.load(store / "matrices" / filename, mmap_mode="r")
        results[context] = run_context(matrix, candidates, queries, truth)
        print(f"[bm1] {context}: {results[context]}")

    matrix = np.load(store / "matrices" / "kprl_cp_zscore.npy", mmap_mode="r")
    results["kprl_tier"] = run_context(matrix, renal_rows, queries_renal, truth, tier_w)
    print(f"[bm1] kprl_tier: {results['kprl_tier']}")

    n_eff = (cp_index["n_renal_sigs"] * cp_index["renal_reliability"]).to_numpy(dtype=np.float32)
    renal = np.load(store / "matrices" / "renal_epi_cp_zscore.npy", mmap_mode="r")
    pan = np.load(store / "matrices" / "pan_cp_zscore.npy", mmap_mode="r")
    for kappa in (0.5, 1.0, 2.0, 4.0, 8.0):
        lam = np.where(cp_index["n_renal_sigs"] > 0, n_eff / (n_eff + kappa), 0).astype(np.float32)
        variant = lam[:, None] * renal + (1 - lam)[:, None] * pan
        key = f"kprl_kappa_{kappa:g}"
        results[key] = run_context(variant, renal_rows, queries_renal, truth)
        print(f"[bm1] {key}: {results[key]}")
        del variant
    best = max(results, key=lambda k: results[k]["recall@1%"])
    results_best = {"best_by_recall@1%": best, "value": results[best]["recall@1%"]}
    print(f"[bm1] best: {results_best}")

    payload = {"n_moa_compounds": int(len(annotated)),
               "n_queries_pan": int(len(queries_all)),
               "n_queries_renal": int(len(queries_renal)),
               "metrics": results, "best": results_best}
    (OUT / "bm1_moa_retrieval.json").write_text(json.dumps(payload, indent=2))
    print(f"[bm1] wrote {OUT / 'bm1_moa_retrieval.json'}")


if __name__ == "__main__":
    main()
