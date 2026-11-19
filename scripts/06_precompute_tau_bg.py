#!/usr/bin/env python
"""Precompute K-PRL gene ranks and per-compound null score tables for the
renal tau calibration (random gene sets of matched input size)."""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load_settings, paths

METHODS = ("xsum", "zhang", "wtcs")


def build_ranks(matrix, out_path):
    if out_path.exists():
        print(f"[ranks] exists {out_path}")
        return np.load(out_path, mmap_mode="r")
    n_drugs, n_genes = matrix.shape
    ranks = np.empty((n_drugs, n_genes), dtype=np.int16)
    order = np.empty((n_drugs, n_genes), dtype=np.int32)
    positions = np.arange(n_genes, dtype=np.int16)[None, :]
    step = 1000
    for start in range(0, n_drugs, step):
        block = np.asarray(matrix[start:start + step])
        idx = np.argsort(-block, axis=1)
        order[start:start + step] = idx
        np.put_along_axis(ranks[start:start + step], idx, positions, axis=1)
        print(f"  ranks {min(start + step, n_drugs)}/{n_drugs}", flush=True)
    np.save(out_path, ranks)
    print(f"[ranks] wrote {out_path}")
    return np.load(out_path, mmap_mode="r")


def xsum_scores(matrix, up_idx, dn_idx):
    return (np.asarray(matrix[:, up_idx]).mean(axis=1)
            - np.asarray(matrix[:, dn_idx]).mean(axis=1))


def zhang_scores(ranks, up_idx, dn_idx, n_genes):
    up = n_genes - np.asarray(ranks[:, up_idx], dtype=np.float32)
    dn = n_genes - np.asarray(ranks[:, dn_idx], dtype=np.float32)
    return (up.mean(axis=1) - dn.mean(axis=1)) / n_genes


def signed_es(ranks, idx, n_genes):
    """Weighted GSEA enrichment score of a gene set on each ranked profile."""
    pos = np.sort(np.asarray(ranks[:, idx]), axis=1).astype(np.float32)
    k = pos.shape[1]
    j = np.arange(k, dtype=np.float32)[None, :]
    misses_before = pos - j
    rs_after = (j + 1) / k - misses_before / (n_genes - k)
    rs_before = j / k - misses_before / (n_genes - k)
    hi = np.maximum(rs_after.max(axis=1), 0.0)
    lo = np.minimum(rs_before.min(axis=1), 0.0)
    return np.where(np.abs(hi) >= np.abs(lo), hi, lo)


def wtcs_scores(ranks, up_idx, dn_idx, n_genes):
    es_up = signed_es(ranks, up_idx, n_genes)
    es_dn = signed_es(ranks, dn_idx, n_genes)
    opposite = np.sign(es_up) * np.sign(es_dn) < 0
    return np.where(opposite, -(es_up - es_dn) / 2.0, 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", type=int, default=40)
    ap.add_argument("--sizes", type=int, nargs="+", default=[20, 50, 100, 200, 400])
    ap.add_argument("--seed", type=int, default=20261119)
    args = ap.parse_args()

    t0 = time.time()
    store = paths()["store"]
    mdir = store / "matrices"
    matrix = np.load(mdir / "kprl_cp_zscore.npy", mmap_mode="r")
    n_drugs, n_genes = matrix.shape
    ranks = build_ranks(matrix, mdir / "kprl_ranks.npy")

    rng = np.random.default_rng(args.seed)
    tables = {}
    for size in args.sizes:
        acc = {m: [] for m in METHODS}
        for _ in range(args.sets):
            genes = rng.choice(n_genes, size=2 * size, replace=False)
            up_idx, dn_idx = genes[:size], genes[size:]
            acc["xsum"].append(xsum_scores(matrix, up_idx, dn_idx))
            acc["zhang"].append(zhang_scores(ranks, up_idx, dn_idx, n_genes))
            acc["wtcs"].append(wtcs_scores(ranks, up_idx, dn_idx, n_genes))
        for method in METHODS:
            vals = np.stack(acc[method])
            tables[f"{method}_mean_{size}"] = vals.mean(axis=0).astype(np.float32)
            tables[f"{method}_std_{size}"] = vals.std(axis=0).astype(np.float32)
        print(f"[null] size={size} sets={args.sets} done ({time.time() - t0:.0f}s)", flush=True)

    out = mdir / "tau_null_tables.npz"
    np.savez_compressed(out, **tables)
    meta = {"sizes": args.sizes, "sets": args.sets, "seed": args.seed,
            "methods": list(METHODS), "n_compounds": n_drugs,
            "calibration": "per-compound random-gene-set null on K-PRL"}
    (store / "models" / "tau_null_meta.json").write_text(json.dumps(meta, indent=2))
    print(f"[done] {out} ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
