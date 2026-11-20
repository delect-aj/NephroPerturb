"""Shared helpers for NephroPerturb build scripts."""
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]

CTL_PREFIX = "ctl_"
CP_TYPE = "trt_cp"


def load_settings():
    with open(ROOT / "config" / "settings.yaml") as fh:
        return yaml.safe_load(fh)


def paths():
    s = load_settings()["paths"]
    return {k: Path(v) for k, v in s.items()}


def phase_specs():
    return load_settings()["phases"]


def read_tsv_gz(path):
    return pd.read_csv(path, sep="\t", dtype=str, compression="gzip")


def decode(arr):
    return np.array([x.decode() if isinstance(x, bytes) else str(x) for x in arr])


def gctx_ids(path):
    with h5py.File(path, "r") as fh:
        col = decode(fh["/0/META/COL/id"][:])
        row = decode(fh["/0/META/ROW/id"][:])
    return col, row


def load_sig_table(cfg=None):
    """All non-control signatures joined across phases with matrix column index.

    Keeps pert_idose / pert_itime (empty string when the phase lacks them) so
    dose/time can inform consensus weighting and filtering.
    """
    cfg = cfg or load_settings()
    lv = Path(cfg["paths"]["level5"])
    frames = []
    col_ids = {}
    keep = ["sig_id", "pert_id", "pert_iname", "pert_type", "cell_id",
            "phase", "col_idx", "pert_idose", "pert_itime"]
    for phase, spec in cfg["phases"].items():
        cols, _ = gctx_ids(lv / spec["matrix"])
        col_ids[phase] = {sid: i for i, sid in enumerate(cols)}
        meta = read_tsv_gz(lv / spec["sig"])
        meta["phase"] = phase
        meta["col_idx"] = [col_ids[phase].get(s) for s in meta["sig_id"]]
        missing = meta["col_idx"].isna()
        if missing.any():
            print(f"[warn] {phase}: {int(missing.sum())} sig_info rows absent from gctx")
        meta = meta[~missing].copy()
        meta["col_idx"] = meta["col_idx"].astype(np.int64)
        for col in ("pert_idose", "pert_itime"):
            if col not in meta.columns:
                meta[col] = ""
            meta[col] = meta[col].fillna("")
        frames.append(meta[keep])
    sigs = pd.concat(frames, ignore_index=True)
    sigs = sigs[~sigs["pert_type"].str.startswith(CTL_PREFIX)].reset_index(drop=True)
    return sigs


def load_gene_universe(cfg=None):
    cfg = cfg or load_settings()
    store = Path(cfg["paths"]["store"])
    path = store / "genes" / "gene_universe.parquet"
    if not path.exists():
        raise SystemExit(f"missing {path}; run scripts/01_build_gene_universe.py first")
    return pd.read_parquet(path)


def phase_row_alignment(cfg, universe):
    """Per-phase index that reorders gctx rows into universe order."""
    lv = Path(cfg["paths"]["level5"])
    wanted = universe["entrez_id"].astype(str).to_numpy()
    align = {}
    for phase, spec in cfg["phases"].items():
        _, row = gctx_ids(lv / spec["matrix"])
        lookup = {gid: i for i, gid in enumerate(row)}
        idx = np.array([lookup[g] for g in wanted], dtype=np.int64)
        align[phase] = idx
    return align


def describe(arr):
    return f"{arr.shape} {arr.dtype}"
