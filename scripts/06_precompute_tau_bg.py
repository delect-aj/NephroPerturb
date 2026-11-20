#!/usr/bin/env python
"""Precompute per-context ranks, |z|-ranks, and the REAL-BIOLOGY tau
calibration tables.

Background library (M = 600, zero kidney leakage):
  600 independent LINCS genetic/ligand consensus profiles
  (pert_type trt_oe / trt_xpr / trt_lig, none of them nephrology cohorts),
  each turned into a signed up/down query at size 50 / 150 / 300
  (up = top-N by z, down = bottom-N by z). Fixed seed 20261119; the manifest
  (sorted pert_ids + sizes + seed) is SHA256-stamped in
  models/tau_background_meta.json.

For every scoring context and kernel the full library is scored against all
600 background queries; each compound's 600 scores are compressed into a
101-point quantile table (21299 x 101 float32) so the online tau is the
empirical signed percentile against real biological queries.

Outputs (atomic):
  matrices/{kprl_ranks|<ctx>_cp_ranks}.npy     descending z ranks (int16)
  matrices/<ctx>_absranks.npy                  descending |z| ranks (int16)
  matrices/tau_null_tables_<ctx>.npz           {method}_quantiles tables
  models/tau_background_meta.json
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))
from common import paths  # noqa: E402

METHODS = ("xsum", "zhang", "wtcs", "func")
CONTEXTS = {
    "kprl": dict(matrix="kprl_cp_zscore.npy", ranks="kprl_ranks.npy"),
    "pan": dict(matrix="pan_cp_zscore.npy", ranks="pan_cp_ranks.npy"),
    "renal_epi": dict(matrix="renal_epi_cp_zscore.npy", ranks="renal_epi_cp_ranks.npy"),
    "renal_endo": dict(matrix="renal_endo_cp_zscore.npy", ranks="renal_endo_cp_ranks.npy"),
    "renal_immune": dict(matrix="renal_immune_cp_zscore.npy",
                         ranks="renal_immune_cp_ranks.npy"),
}
BG_TYPES = ("trt_oe", "trt_xpr", "trt_lig")
BG_SIZES = (50, 150, 300)


def build_ranks(matrix, out_path, absolute=False):
    if out_path.exists():
        print(f"[ranks] exists {out_path}")
        return np.load(out_path, mmap_mode="r")
    n_drugs, n_genes = matrix.shape
    ranks = np.empty((n_drugs, n_genes), dtype=np.int16)
    positions = np.arange(n_genes, dtype=np.int16)[None, :]
    step = 1000
    for start in range(0, n_drugs, step):
        block = np.asarray(matrix[start:start + step])
        order = np.argsort(-np.abs(block) if absolute else -block, axis=1)
        np.put_along_axis(ranks[start:start + step], order, positions, axis=1)
        print(f"  ranks {min(start + step, n_drugs)}/{n_drugs}", flush=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp.npy")
    np.save(tmp, ranks)
    tmp.replace(out_path)
    print(f"[ranks] wrote {out_path}")
    return np.load(out_path, mmap_mode="r")


def sample_background(store, seed, m=600):
    """600 signed up/down queries from in-house genetic/ligand profiles."""
    genetic = pd.read_parquet(store / "genetic_index.parquet")
    elig = genetic[genetic["pert_type"].isin(BG_TYPES)].reset_index(drop=True)
    if len(elig) < m:
        raise SystemExit(f"only {len(elig)} eligible genetic profiles, need {m}")
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(elig), size=m, replace=False)
    gen_mat = np.load(store / "matrices" / "genetic_consensus.npy", mmap_mode="r")
    universe = pd.read_parquet(store / "genes" / "gene_universe.parquet")
    symbols = universe["symbol"].tolist()
    rng2 = np.random.default_rng(seed + 1)
    sizes = [BG_SIZES[i % len(BG_SIZES)] for i in range(m)]
    rng2.shuffle(sizes)
    sigs = []
    for j, (idx, size) in enumerate(zip(pick, sizes)):
        row = int(elig["matrix_row_idx"].iloc[idx])
        z = np.asarray(gen_mat[row], dtype=np.float32)
        order = np.argsort(-z)
        up = list(order[:size])
        dn = list(order[::-1][:size])
        up_sym = [symbols[i] for i in up]
        dn_sym = [symbols[i] for i in dn]
        sigs.append({"pert_id": elig["pert_id"].iloc[idx],
                     "pert_type": elig["pert_type"].iloc[idx],
                     "size": int(size), "up": up, "down": dn,
                     "up_symbols": up_sym, "down_symbols": dn_sym})
        if j % 100 == 0:
            print(f"  background {j}/{m}", flush=True)
    return sigs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contexts", nargs="+", default=list(CONTEXTS))
    ap.add_argument("--seed", type=int, default=20261119)
    ap.add_argument("--background", type=int, default=600)
    args = ap.parse_args()

    from app.core.store import MatrixStore
    from app.engine import scoring

    t0 = time.time()
    store = paths()["store"]
    mdir = store / "matrices"
    mdir.mkdir(parents=True, exist_ok=True)
    mstore = MatrixStore()

    bg = sample_background(store, args.seed, args.background)
    manifest = {"seed": args.seed, "n": len(bg),
                "sizes": sorted(set(s["size"] for s in bg)),
                "types": list(BG_TYPES),
                "idents": sorted(f"{s['pert_id']}|{s['size']}" for s in bg)}
    sha = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    meta_path = store / "models" / "tau_background_meta.json"
    meta_path.write_text(json.dumps({**manifest, "sha256": sha}, indent=2))
    print(f"[bg] {len(bg)} signatures, manifest sha256={sha[:16]}")

    matrix_keys = {"kprl": "kprl_cp_zscore", "pan": "pan_cp_zscore",
                   "renal_epi": "renal_epi_cp_zscore",
                   "renal_endo": "renal_endo_cp_zscore",
                   "renal_immune": "renal_immune_cp_zscore"}
    for ctx in args.contexts:
        spec = CONTEXTS[ctx]
        matrix = np.load(mdir / spec["matrix"], mmap_mode="r")
        build_ranks(matrix, mdir / spec["ranks"], absolute=False)
        build_ranks(matrix, mdir / f"{ctx}_absranks.npy", absolute=True)
        # random-gene-set scoring over a 1 GB mmap is page-fault bound; hold the
        # matrix and ranks in RAM (one context per process)
        matrix = np.ascontiguousarray(matrix)
        mstore._matrices[matrix_keys[ctx]] = matrix
        scoring._RANK_CACHE[(str(mstore.store), "z", ctx)] = np.ascontiguousarray(
            np.load(mdir / spec["ranks"]))
        scoring._RANK_CACHE[(str(mstore.store), "abs", ctx)] = np.ascontiguousarray(
            np.load(mdir / f"{ctx}_absranks.npy"))

        tables = {}
        for method in METHODS:
            scores = np.zeros((matrix.shape[0], len(bg)), dtype=np.float32)
            for j, sig in enumerate(bg):
                if method == "xsum":
                    s = scoring.xsum_extreme(mstore, ctx, sig["up"], sig["down"])
                elif method == "zhang":
                    s = scoring.zhang_score(mstore, ctx, sig["up"], sig["down"])
                elif method == "wtcs":
                    s = scoring.wtcs_score(mstore, ctx, sig["up"], sig["down"])
                else:
                    s = scoring.func_scores(mstore, sig["up_symbols"],
                                            sig["down_symbols"], ctx)
                scores[:, j] = s
                if j % 150 == 0:
                    print(f"  [{ctx}/{method}] {j}/{len(bg)} ({time.time() - t0:.0f}s)",
                          flush=True)
            tables[f"{method}_quantiles"] = np.quantile(
                scores, np.linspace(0.0, 1.0, 101), axis=1).T.astype(np.float32)
            print(f"[tau] {ctx}/{method} quantiles {tables[f'{method}_quantiles'].shape}")

        out = mdir / f"tau_null_tables_{ctx}.npz"
        tmp = out.with_suffix(out.suffix + ".tmp.npz")
        np.savez_compressed(tmp, **tables)
        tmp.replace(out)
        print(f"[done] {ctx} -> {out} ({time.time() - t0:.0f}s)", flush=True)

    print(f"[all done] {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
