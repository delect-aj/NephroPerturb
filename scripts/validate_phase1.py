#!/usr/bin/env python
"""Structural + biological sanity checks for the Phase 1 matrices."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import paths

# canonical, well-established L1000 responses used as direction controls
CHECKS = [
    ("geldanamycin", [("HSPA1A", +1), ("HSPA1B", +1), ("HSPH1", +1)]),
    ("vorinostat", [("CDKN1A", +1), ("HIST1H2BM", -1), ("CCND1", -1)]),
    ("dexamethasone", [("TSC22D3", +1), ("FKBP5", +1), ("DUSP1", +1)]),
    ("trichostatin-a", [("CDKN1A", +1)]),
    ("sirolimus", [("DDIT4", -1), ("BNIP3", -1)]),
]


def main():
    store = paths()["store"]
    mdir = store / "matrices"
    genes = pd.read_parquet(store / "genes" / "gene_universe.parquet")
    idx = pd.read_parquet(store / "cp_index.parquet")
    sym2col = dict(zip(genes["symbol"].str.upper(), genes["matrix_col_idx"]))

    matrices = {}
    for name in ("kprl_cp_zscore", "pan_cp_zscore", "renal_epi_cp_zscore",
                 "renal_endo_cp_zscore", "renal_immune_cp_zscore"):
        arr = np.load(mdir / f"{name}.npy", mmap_mode="r")
        assert arr.shape == (len(idx), len(genes)), (name, arr.shape)
        assert arr.dtype == np.float32
        matrices[name] = arr
        finite = np.isfinite(np.asarray(arr[::97])).mean()
        assert finite == 1.0, f"{name} has non-finite values"
        print(f"[ok] {name} {arr.shape} {arr.dtype}")

    for name in ("renal_endo_cp_zscore", "renal_immune_cp_zscore"):
        nz = int((np.abs(np.asarray(matrices[name])).sum(axis=1) > 0).sum())
        print(f"[info] {name}: {nz} compounds with signal")

    lam = idx["kprl_lambda"].to_numpy()
    assert lam.min() >= 0 and lam.max() <= 1
    print(f"[ok] lambda mean={lam.mean():.3f} median={np.median(lam):.3f} "
          f"n_zero={(lam == 0).sum()} n>0.5={(lam > 0.5).sum()}")

    failures = []
    for pert, checks in CHECKS:
        hit = idx[idx["pert_id"].str.lower() == pert.lower()]
        if hit.empty:
            hit = idx[idx["pert_iname"].str.lower() == pert.lower()]
        if hit.empty:
            print(f"[skip] {pert} not found")
            continue
        row = int(hit.iloc[0]["matrix_row_idx"])
        for gene, sign in checks:
            col = sym2col.get(gene.upper())
            if col is None:
                print(f"[skip] {pert}/{gene} absent from gene universe")
                continue
            vals = {k: float(matrices[k][row, col]) for k in
                    ("kprl_cp_zscore", "pan_cp_zscore", "renal_epi_cp_zscore")}
            ok = np.sign(vals["kprl_cp_zscore"]) == sign
            tag = "ok" if ok else "FAIL"
            print(f"[{tag}] {pert:16s} {gene:10s} expect {sign:+d} "
                  f"kprl={vals['kprl_cp_zscore']:+.2f} pan={vals['pan_cp_zscore']:+.2f} "
                  f"renal={vals['renal_epi_cp_zscore']:+.2f}")
            if not ok:
                failures.append((pert, gene, vals))

    for name in ("KPRL", "PanCell", "RenalEpi"):
        up = mdir.parent / "downloads" / f"{name}_UP_250.gmt"
        dn = mdir.parent / "downloads" / f"{name}_DN_250.gmt"
        if not up.exists():
            continue
        n_up = sum(1 for _ in open(up))
        n_dn = sum(1 for _ in open(dn))
        assert n_up == len(idx) and n_dn == len(idx), (name, n_up, n_dn)
        print(f"[ok] {name} GMT: {n_up} up rows / {n_dn} down rows")

    if failures:
        print(f"\n{len(failures)} direction control failures")
        sys.exit(1)
    print("\nvalidation passed")


if __name__ == "__main__":
    main()
