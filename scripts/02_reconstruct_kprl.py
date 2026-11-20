#!/usr/bin/env python
"""Reconstruct Pan-Cell / Renal-Microenv / K-PRL continuous MODZ consensus
matrices from LINCS Level 5 GCTX with MODZ-style weighting.

Weighted consensus (per compound d, per context group g, signatures i):
    s_i = clip(mean(|z_i| on Landmark genes), 0.1, 5.0)          signal strength
    c_i = mean Pearson r(z_i, centroid of the other sigs)         (m >= 3 only)
    w_i = max(0.05, c_i) * s_i**gamma        gamma=0.5, m<3 -> c_i := 1
    Z_d = sum(w_i z_i) / sum(w_i)

Two passes over GCTX: pass 1 accumulates Landmark sums/counts and plain
arithmetic sums (legacy *_amean outputs); pass 2 computes per-signature
weights and weighted full-gene accumulations.

Outputs (atomic writes):
  pan/renal_epi/renal_endo/renal_immune_cp_zscore.npy   weighted MODZ means
  pan_cp_amean.npy, renal_epi_cp_amean.npy             legacy arithmetic means
  scan/kprl_k<K>.npy                                    K-PRL for kappa scan
  kprl_cp_zscore.npy                                    K-PRL at settings kappa
  genetic_consensus.npy                                 (unchanged method)
  cp_index.parquet, genetic_index.parquet               + tas_renal, concordance
  downloads/*_UP_250.gmt / *_DN_250.gmt

--lock-kappa K copies scan/kprl_kK.npy into the production K-PRL matrix,
updates settings.yaml kappa + cp_index lambdas, and rewrites the GMTs.
"""
import argparse
import sys
import time
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (CP_TYPE, ROOT, load_settings, paths, phase_row_alignment,
                    load_sig_table, phase_specs)

KAPPA_SCAN = (0.5, 1.0, 2.0, 5.0, 10.0, 20.0)
GAMMA = 0.5


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


def atomic_save_npy(path, array):
    tmp = path.with_suffix(path.suffix + ".tmp.npy")
    np.save(tmp, array)
    tmp.replace(path)
    print(f"[save] {path}")


def block_weights(z_lm, group_sum_lm, pid_rows, counts, gamma=GAMMA):
    """MODZ-style weights for a block of signatures of one context group.

    z_lm: (r, n_landmark) values; group_sum_lm: per-compound Landmark sums.
    Returns (w, s, c) with c=NaN where m<3 (weighted as 1.0).
    """
    S = group_sum_lm[pid_rows]
    m = counts[pid_rows].astype(np.float32)
    denom = np.maximum(m - 1.0, 1.0)[:, None]
    centroid = (S - z_lm) / denom
    a = z_lm - z_lm.mean(axis=1, keepdims=True)
    b = centroid - centroid.mean(axis=1, keepdims=True)
    num = (a * b).sum(axis=1)
    den = (np.linalg.norm(a, axis=1) * np.linalg.norm(b, axis=1))
    c = np.where(den > 0, num / np.maximum(den, 1e-9), 0.05)
    m_ok = m >= 3
    c_use = np.where(m_ok, np.maximum(0.05, c), 1.0)
    s = np.clip(np.abs(z_lm).mean(axis=1), 0.1, 5.0)
    w = c_use * s ** gamma
    return w.astype(np.float32), s.astype(np.float32), np.where(m_ok, c, np.nan)


def write_gmt(matrix, pert_ids, names, path_up, path_dn, symbols, top_n=250):
    with open(path_up, "w") as fu, open(path_dn, "w") as fd:
        for i, pid in enumerate(pert_ids):
            row = matrix[i]
            order = np.argsort(-row, kind="stable")
            up = order[:top_n]
            dn = order[::-1][:top_n]
            desc = names.get(pid) or pid
            fu.write(pid + "\t" + desc + "\t" + "\t".join(symbols[up]) + "\n")
            fd.write(pid + "\t" + desc + "\t" + "\t".join(symbols[dn]) + "\n")
    print(f"[gmt] {path_up}")
    print(f"[gmt] {path_dn}")


def kprl_lambda(n_eff, kappa):
    return np.where(n_eff > 0, n_eff / (n_eff + kappa), 0.0).astype(np.float32)


def lock_kappa(kappa):
    """Promote scan/kprl_k<K>.npy to the production matrix and GMTs."""
    store = paths()["store"]
    src = store / "matrices" / "scan" / f"kprl_k{kappa:g}.npy"
    if not src.exists():
        raise SystemExit(f"missing {src}; run the reconstruction first")
    matrix = np.asarray(np.load(src, mmap_mode="r"))
    atomic_save_npy(store / "matrices" / "kprl_cp_zscore.npy", matrix)
    idx = pd.read_parquet(store / "cp_index.parquet")
    lam = kprl_lambda(idx["kprl_effective_n"].to_numpy(dtype=np.float32), kappa)
    idx["kprl_lambda"] = lam
    idx.to_parquet(store / "cp_index.parquet", index=False)
    cfg_path = ROOT / "config" / "settings.yaml"
    text = cfg_path.read_text()
    import re
    text = re.sub(r"(\n  kappa:\s*)[0-9.]+", rf"\g<1>{kappa:g}", text)
    cfg_path.write_text(text)
    genes = pd.read_parquet(store / "genes" / "gene_universe.parquet")
    names = idx.set_index("pert_id")["pert_iname"].to_dict()
    symbols = genes["symbol"].to_numpy()
    ddir = store / "downloads"
    write_gmt(matrix, idx["pert_id"].tolist(), names,
              ddir / "KPRL_UP_250.gmt", ddir / "KPRL_DN_250.gmt", symbols)
    print(f"[lock] kappa={kappa} -> kprl_cp_zscore.npy + settings + GMTs")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kappa", type=float, default=None)
    ap.add_argument("--gamma", type=float, default=GAMMA)
    ap.add_argument("--lock-kappa", type=float, default=None)
    args = ap.parse_args()

    if args.lock_kappa is not None:
        lock_kappa(args.lock_kappa)
        return

    t0 = time.time()
    cfg = load_settings()
    kappa = args.kappa if args.kappa is not None else float(cfg["kprl"]["kappa"])
    lv = paths()["level5"]
    store = paths()["store"]
    mdir = store / "matrices"
    ddir = store / "downloads"
    (mdir / "scan").mkdir(parents=True, exist_ok=True)
    ddir.mkdir(parents=True, exist_ok=True)

    universe = pd.read_parquet(store / "genes" / "gene_universe.parquet")
    symbols = universe["symbol"].to_numpy()
    n_genes = len(universe)
    lm_idx = np.flatnonzero(universe["is_landmark"].to_numpy() == 1)
    rel_mask = (universe["is_bing"] == 1).to_numpy() if cfg["kprl"]["reliability_genes"] == "bing" \
        else (universe["is_landmark"] == 1).to_numpy()
    n_lm = len(lm_idx)

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
    group_cells = {
        "renal_epi": set(ctx["renal_epi"]),
        "endothelial": set(ctx["endothelial"]),
        "immune": set(ctx["immune"]),
    }
    groups = ["pan", "renal_epi", "endothelial", "immune"]
    cp_group = {"pan": np.ones(len(cp), dtype=bool)}
    for name, cells in group_cells.items():
        cp_group[name] = cp["cell_id"].isin(cells).to_numpy()
    cp_counts = {}
    for g in groups:
        pid = np.array([cp_idx[p] for p in cp.loc[cp_group[g], "pert_id"]], dtype=np.int64)
        cp_counts[g] = np.bincount(pid, minlength=n_cp)
    gen_counts = np.bincount(np.array([gen_idx[p] for p in gen["pert_id"]], dtype=np.int64),
                             minlength=n_gen)
    print("[counts] renal_epi sigs:", int(cp_counts["renal_epi"].sum()),
          "| perts with renal sigs:", int((cp_counts["renal_epi"] > 0).sum()))

    # ---------------- pass 1: Landmark sums, plain sums, genetic ----------------
    sum_lm = {g: np.zeros((n_cp, n_lm), dtype=np.float32) for g in groups}
    plain = {"pan": np.zeros((n_cp, n_genes), dtype=np.float32),
             "renal_epi": np.zeros((n_cp, n_genes), dtype=np.float32)}
    gen_acc = np.zeros((n_gen, n_genes), dtype=np.float32)
    block_size = int(cfg["build"]["cols_per_block"])

    def iter_blocks(tag):
        for phase, spec in phase_specs().items():
            sel = sigs[sigs["phase"] == phase].sort_values("col_idx").reset_index(drop=True)
            cols = sel["col_idx"].to_numpy()
            rows = align[phase]
            with h5py.File(lv / spec["matrix"], "r") as fh:
                for start in range(0, len(cols), block_size):
                    sl = slice(start, min(start + block_size, len(cols)))
                    data = read_block(fh, cols[sl], rows)
                    yield tag, phase, sel.iloc[sl].reset_index(drop=True), data
                    del data
                    if start and start % (block_size * 10) == 0:
                        print(f"  {tag} {phase}: {start}/{len(cols)} "
                              f"({time.time() - t0:.0f}s)", flush=True)

    for _, phase, sel, data in iter_blocks("pass1"):
        is_cp = (sel["pert_type"] == CP_TYPE).to_numpy()
        cell = sel["cell_id"].to_numpy()
        pid_cp = np.array([cp_idx.get(p, -1) for p in sel["pert_id"]], dtype=np.int64)
        pid_gen = np.array([gen_idx.get(p, -1) for p in sel["pert_id"]], dtype=np.int64)
        cp_rows = np.flatnonzero(is_cp)
        if len(cp_rows):
            add_rows(plain["pan"], pid_cp[cp_rows], data[cp_rows])
            for g in groups:
                if g == "pan":
                    idx = cp_rows
                elif g in group_cells:
                    idx = cp_rows[np.isin(cell[cp_rows], list(group_cells[g]))]
                else:
                    continue
                if len(idx):
                    add_rows(sum_lm[g], pid_cp[idx], data[idx][:, lm_idx])
            ren = cp_rows[np.isin(cell[cp_rows], list(group_cells["renal_epi"]))]
            if len(ren):
                add_rows(plain["renal_epi"], pid_cp[ren], data[ren])

        gen_rows = np.flatnonzero(~is_cp)
        if len(gen_rows):
            add_rows(gen_acc, pid_gen[gen_rows], data[gen_rows])
    print(f"[pass1] done {time.time() - t0:.0f}s")

    # ---------------- pass 2: weighted accumulation ----------------
    acc = {g: np.zeros((n_cp, n_genes), dtype=np.float32) for g in groups}
    accsq_renal = np.zeros((n_cp, n_genes), dtype=np.float32)
    wsum = {g: np.zeros(n_cp, dtype=np.float64) for g in groups}
    stat_w = np.zeros(n_cp, dtype=np.float64)
    stat_ws = np.zeros(n_cp, dtype=np.float64)
    stat_wc = np.zeros(n_cp, dtype=np.float64)
    stat_wc_n = np.zeros(n_cp, dtype=np.float64)

    for _, phase, sel, data in iter_blocks("pass2"):
        is_cp = (sel["pert_type"] == CP_TYPE).to_numpy()
        cell = sel["cell_id"].to_numpy()
        pid_cp = np.array([cp_idx.get(p, -1) for p in sel["pert_id"]], dtype=np.int64)
        cp_rows = np.flatnonzero(is_cp)
        if len(cp_rows):
            z_lm = data[:, lm_idx]
            group_rows = {"pan": cp_rows,
                          "renal_epi": cp_rows[np.isin(cell[cp_rows], list(group_cells["renal_epi"]))],
                          "endothelial": cp_rows[np.isin(cell[cp_rows], list(group_cells["endothelial"]))],
                          "immune": cp_rows[np.isin(cell[cp_rows], list(group_cells["immune"]))]}
            for g, idx in group_rows.items():
                if not len(idx):
                    continue
                pids = pid_cp[idx]
                w, s, c = block_weights(z_lm[idx], sum_lm[g], pids, cp_counts[g], args.gamma)
                weighted = data[idx] * w[:, None]
                add_rows(acc[g], pids, weighted)
                np.add.at(wsum[g], pids, w.astype(np.float64))
                if g == "renal_epi":
                    add_rows(accsq_renal, pids, weighted * data[idx])
                    np.add.at(stat_w, pids, w.astype(np.float64))
                    np.add.at(stat_ws, pids, (w * s).astype(np.float64))
                    ok = ~np.isnan(c)
                    np.add.at(stat_wc, pids[ok], (w[ok] * c[ok]).astype(np.float64))
                    np.add.at(stat_wc_n, pids[ok], w[ok].astype(np.float64))
                del weighted
            del z_lm
    print(f"[pass2] done {time.time() - t0:.0f}s")

    means = {}
    for g in groups:
        denom = np.maximum(wsum[g], 1e-12)[:, None].astype(np.float32)
        means[g] = acc[g] / denom
        del acc[g]
    c_renal = np.maximum(wsum["renal_epi"], 1e-12)[:, None].astype(np.float32)
    var = accsq_renal / c_renal - means["renal_epi"] ** 2
    sd_renal = np.sqrt(np.clip(var, 0, None))
    del accsq_renal, var

    has_renal = cp_counts["renal_epi"] > 0
    mean_abs = np.abs(means["renal_epi"][:, rel_mask]).mean(axis=1)
    mean_sd = sd_renal[:, rel_mask].mean(axis=1)
    reliability = np.where(has_renal, mean_abs / (mean_abs + mean_sd + 1e-12), 0.0)
    n_eff = cp_counts["renal_epi"] * reliability
    tas_renal = np.where(stat_w > 0, stat_ws / np.maximum(stat_w, 1e-12), 0.0)
    concordance = np.where(stat_wc_n > 0, stat_wc / np.maximum(stat_wc_n, 1e-12), np.nan)

    amean_pan = plain["pan"] / np.maximum(cp_counts["pan"], 1).astype(np.float32)[:, None]
    amean_renal = plain["renal_epi"] / np.maximum(cp_counts["renal_epi"], 1).astype(np.float32)[:, None]
    del plain

    atomic_save_npy(mdir / "pan_cp_zscore.npy", means["pan"])
    atomic_save_npy(mdir / "renal_epi_cp_zscore.npy", means["renal_epi"])
    atomic_save_npy(mdir / "renal_endo_cp_zscore.npy", means["endothelial"])
    atomic_save_npy(mdir / "renal_immune_cp_zscore.npy", means["immune"])
    atomic_save_npy(mdir / "pan_cp_amean.npy", amean_pan)
    atomic_save_npy(mdir / "renal_epi_cp_amean.npy", amean_renal)

    for k in KAPPA_SCAN:
        lam = kprl_lambda(n_eff, k)
        variant = lam[:, None] * means["renal_epi"] + (1 - lam)[:, None] * means["pan"]
        atomic_save_npy(mdir / "scan" / f"kprl_k{k:g}.npy", variant)
        del variant
    lam = kprl_lambda(n_eff, kappa)
    kprl = lam[:, None] * means["renal_epi"] + (1 - lam)[:, None] * means["pan"]
    atomic_save_npy(mdir / "kprl_cp_zscore.npy", kprl)

    gen_counts32 = np.maximum(gen_counts, 1).astype(np.float32)[:, None]
    atomic_save_npy(mdir / "genetic_consensus.npy", gen_acc / gen_counts32)

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
        "kprl_effective_n": n_eff.astype(np.float32),
        "tas_renal": tas_renal.astype(np.float32),
        "renal_concordance": concordance.astype(np.float32),
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

    print(f"[kprl] kappa={kappa:g} lambda: mean={lam.mean():.3f} "
          f"median={np.median(lam):.3f} zero={(lam == 0).sum()} full={(lam > 0.9).sum()}")
    print(f"[kprl] tas_renal mean={np.nanmean(tas_renal):.3f} "
          f"concordance mean={np.nanmean(concordance):.3f}")
    print(f"[time] {time.time() - t0:.0f}s")

    write_gmt(kprl, cp_perts, names, ddir / "KPRL_UP_250.gmt", ddir / "KPRL_DN_250.gmt", symbols)
    write_gmt(means["pan"], cp_perts, names, ddir / "PanCell_UP_250.gmt",
              ddir / "PanCell_DN_250.gmt", symbols)
    write_gmt(means["renal_epi"], cp_perts, names, ddir / "RenalEpi_UP_250.gmt",
              ddir / "RenalEpi_DN_250.gmt", symbols)


if __name__ == "__main__":
    main()
