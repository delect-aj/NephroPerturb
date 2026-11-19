#!/usr/bin/env python
"""Reconstruct Pan-Cell / Renal-Microenv / K-PRL continuous MODZ consensus
matrices from LINCS Level 5 GCTX, plus split UP_250 / DN_250 GMT exports."""
import argparse
import sys
import time
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (CP_TYPE, load_settings, paths, phase_row_alignment,
                    load_sig_table, phase_specs)


def add_rows(target, pert_idx, data):
    """Accumulate block rows (n_cols x n_genes) into target[pert]."""
    if len(pert_idx) == 0:
        return
    order = np.argsort(pert_idx, kind="stable")
    uniq, starts = np.unique(pert_idx[order], return_index=True)
    target[uniq] += np.add.reduceat(data[order], starts, axis=0)


def read_block(fh, sig_cols, gene_order):
    """GCTX matrix is stored as [signature, gene]; returns (n_sigs, n_genes)."""
    if (np.diff(sig_cols) == 1).all():
        block = fh["/0/DATA/0/matrix"][sig_cols[0]:sig_cols[-1] + 1, :]
    else:
        block = fh["/0/DATA/0/matrix"][sig_cols, :]
    return np.ascontiguousarray(block[:, gene_order])


def write_gmt(matrix, pert_ids, names, path_up, path_dn, top_n=250):
    with open(path_up, "w") as fu, open(path_dn, "w") as fd:
        for i, pid in enumerate(pert_ids):
            row = matrix[i]
            order = np.argsort(-row, kind="stable")
            up = order[:top_n]
            dn = order[::-1][:top_n]
            desc = names.get(pid) or pid
            fu.write(pid + "\t" + desc + "\t" + "\t".join(SYMBOLS[up]) + "\n")
            fd.write(pid + "\t" + desc + "\t" + "\t".join(SYMBOLS[dn]) + "\n")
    print(f"[gmt] {path_up}")
    print(f"[gmt] {path_dn}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kappa", type=float, default=None)
    ap.add_argument("--max-cols", type=int, default=0,
                    help="smoke test: only read the first N signature columns")
    args = ap.parse_args()

    global SYMBOLS
    t0 = time.time()
    cfg = load_settings()
    kappa = args.kappa if args.kappa is not None else float(cfg["kprl"]["kappa"])
    lv = paths()["level5"]
    store = paths()["store"]
    mdir = store / "matrices"
    ddir = store / "downloads"
    mdir.mkdir(parents=True, exist_ok=True)
    ddir.mkdir(parents=True, exist_ok=True)

    universe = pd.read_parquet(store / "genes" / "gene_universe.parquet")
    SYMBOLS = universe["symbol"].to_numpy()
    n_genes = len(universe)
    rel_mask = (universe["is_bing"] == 1).to_numpy() if cfg["kprl"]["reliability_genes"] == "bing" \
        else (universe["is_landmark"] == 1).to_numpy()

    sigs = load_sig_table(cfg)
    align = phase_row_alignment(cfg, universe)
    cp = sigs[sigs["pert_type"] == CP_TYPE].reset_index(drop=True)
    gen = sigs[sigs["pert_type"] != CP_TYPE].reset_index(drop=True)
    cp_perts = list(pd.unique(cp["pert_id"]))
    gen_perts = list(pd.unique(gen["pert_id"]))
    cp_idx = {p: i for i, p in enumerate(cp_perts)}
    gen_idx = {p: i for i, p in enumerate(gen_perts)}
    n_cp, n_gen = len(cp_perts), len(gen_perts)
    print(f"[data] {len(sigs)} treatment signatures | cp={len(cp)} ({n_cp} perts) | "
          f"genetic/ligand={len(gen)} ({n_gen} perts) | genes={n_genes}")

    ctx = cfg["contexts"]
    group_cols = {
        "renal_epi": set(ctx["renal_epi"]),
        "endothelial": set(ctx["endothelial"]),
        "immune": set(ctx["immune"]),
    }
    cp_group = {"pan": np.ones(len(cp), dtype=bool)}
    for name, cells in group_cols.items():
        cp_group[name] = cp["cell_id"].isin(cells).to_numpy()
    cp_counts = {k: np.bincount(np.array([cp_idx[p] for p in cp.loc[m, "pert_id"]],
                                         dtype=np.int64), minlength=n_cp)
                 for k, m in cp_group.items()}
    gen_counts = np.bincount(np.array([gen_idx[p] for p in gen["pert_id"]], dtype=np.int64),
                             minlength=n_gen)
    print("[counts] renal_epi sigs:", int(cp_counts["renal_epi"].sum()),
          "| perts with renal sigs:", int((cp_counts["renal_epi"] > 0).sum()))

    acc = {k: np.zeros((n_cp, n_genes), dtype=np.float32) for k in cp_counts}
    acc_sq_renal = np.zeros((n_cp, n_genes), dtype=np.float32)
    gen_acc = np.zeros((n_gen, n_genes), dtype=np.float32)

    block_size = int(cfg["build"]["cols_per_block"])
    for phase, spec in phase_specs().items():
        sel = sigs[sigs["phase"] == phase].sort_values("col_idx").reset_index(drop=True)
        if args.max_cols:
            sel = sel.iloc[:args.max_cols]
        cols = sel["col_idx"].to_numpy()
        rows = align[phase]
        is_cp = (sel["pert_type"] == CP_TYPE).to_numpy()
        cell = sel["cell_id"].to_numpy()
        pid_cp = np.array([cp_idx.get(p, -1) for p in sel["pert_id"]], dtype=np.int64)
        pid_gen = np.array([gen_idx.get(p, -1) for p in sel["pert_id"]], dtype=np.int64)
        print(f"[read] {phase}: {len(cols)} columns")
        with h5py.File(lv / spec["matrix"], "r") as fh:
            for start in range(0, len(cols), block_size):
                sl = slice(start, min(start + block_size, len(cols)))
                data = read_block(fh, cols[sl], rows)
                cp_rows = np.flatnonzero(is_cp[sl])
                if len(cp_rows):
                    add_rows(acc["pan"], pid_cp[sl][cp_rows], data[cp_rows])
                    for name, cells in group_cols.items():
                        g = cp_rows[np.isin(cell[sl][cp_rows], list(cells))]
                        add_rows(acc[name], pid_cp[sl][g], data[g])
                        if name == "renal_epi":
                            add_rows(acc_sq_renal, pid_cp[sl][g], data[g] * data[g])
                gen_rows = np.flatnonzero(~is_cp[sl])
                if len(gen_rows):
                    add_rows(gen_acc, pid_gen[sl][gen_rows], data[gen_rows])
                del data
                if start and start % (block_size * 10) == 0:
                    print(f"  {phase}: {start}/{len(cols)} cols "
                          f"({time.time() - t0:.0f}s)")

    means = {}
    for k, a in acc.items():
        c = np.maximum(cp_counts[k], 1).astype(np.float32)[:, None]
        means[k] = a / c
    c_renal = np.maximum(cp_counts["renal_epi"], 1).astype(np.float32)[:, None]
    var = acc_sq_renal / c_renal - means["renal_epi"] ** 2
    sd_renal = np.sqrt(np.clip(var, 0, None))

    has_renal = cp_counts["renal_epi"] > 0
    mean_abs = np.abs(means["renal_epi"][:, rel_mask]).mean(axis=1)
    mean_sd = sd_renal[:, rel_mask].mean(axis=1)
    reliability = np.where(has_renal, mean_abs / (mean_abs + mean_sd + 1e-12), 0.0)
    n_eff = cp_counts["renal_epi"] * reliability
    lam = np.where(has_renal, n_eff / (n_eff + kappa), 0.0).astype(np.float32)
    kprl = lam[:, None] * means["renal_epi"] + (1 - lam)[:, None] * means["pan"]

    np.save(mdir / "pan_cp_zscore.npy", means["pan"])
    np.save(mdir / "renal_epi_cp_zscore.npy", means["renal_epi"])
    np.save(mdir / "renal_endo_cp_zscore.npy", means["endothelial"])
    np.save(mdir / "renal_immune_cp_zscore.npy", means["immune"])
    np.save(mdir / "kprl_cp_zscore.npy", kprl)
    gen_counts32 = np.maximum(gen_counts, 1).astype(np.float32)[:, None]
    np.save(mdir / "genetic_consensus.npy", gen_acc / gen_counts32)

    names = cp.groupby("pert_id")["pert_iname"].first().to_dict()
    index = pd.DataFrame({
        "matrix_row_idx": np.arange(n_cp),
        "pert_id": cp_perts,
        "pert_iname": [names.get(p) for p in cp_perts],
        "n_sigs": cp_counts["pan"],
        "n_renal_sigs": cp_counts["renal_epi"],
        "n_endo_sigs": cp_counts["endothelial"],
        "n_immune_sigs": cp_counts["immune"],
        "renal_reliability": reliability.astype(np.float32),
        "kprl_lambda": lam,
    })
    index.to_parquet(store / "cp_index.parquet", index=False)

    gnames = gen.groupby("pert_id")["pert_iname"].first().to_dict()
    gtypes = gen.groupby("pert_id")["pert_type"].first().to_dict()
    pd.DataFrame({
        "matrix_row_idx": np.arange(n_gen),
        "pert_id": gen_perts,
        "pert_iname": [gnames.get(p) for p in gen_perts],
        "pert_type": [gtypes.get(p) for p in gen_perts],
        "n_sigs": gen_counts,
    }).to_parquet(store / "genetic_index.parquet", index=False)

    print(f"[kprl] lambda: mean={lam.mean():.3f} median={np.median(lam):.3f} "
          f"zero={(lam == 0).sum()} full={(lam > 0.9).sum()}")
    print(f"[time] {time.time() - t0:.0f}s")

    if not args.max_cols:
        write_gmt(kprl, cp_perts, names, ddir / "KPRL_UP_250.gmt", ddir / "KPRL_DN_250.gmt")
        write_gmt(means["pan"], cp_perts, names,
                  ddir / "PanCell_UP_250.gmt", ddir / "PanCell_DN_250.gmt")
        write_gmt(means["renal_epi"], cp_perts, names,
                  ddir / "RenalEpi_UP_250.gmt", ddir / "RenalEpi_DN_250.gmt")


if __name__ == "__main__":
    main()
