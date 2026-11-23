"""Lazy loaders for matrices, annotations and the SQLite metadata database.

Supports both the full `store/` layout and the compact gene-major `store_lite/`
runtime bundle (<2 GB disk, <=1 GB peak RAM on 1 CPU core).
"""
from collections import OrderedDict
import ctypes
import gc
import json
import os
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.lib import format as npf

STORE = Path(os.environ.get("NEPHRO_STORE", "/public/home/dongb/agent/renalkb/store"))
CONFIG = Path(os.environ.get("NEPHRO_CONFIG", "/public/home/dongb/agent/renalkb/config"))

try:
    _LIBC = ctypes.CDLL("libc.so.6")
except Exception:
    _LIBC = None


def trim_memory():
    gc.collect()
    if _LIBC is not None and hasattr(_LIBC, "malloc_trim"):
        try:
            _LIBC.malloc_trim(0)
        except Exception:
            pass


def _parse_npy_header(path: Path):
    with open(path, "rb") as fh:
        major, minor = npf.read_magic(fh)
        if (major, minor) == (1, 0):
            shape, fortran, dtype = npf.read_array_header_1_0(fh)
        elif major >= 2:
            shape, fortran, dtype = npf.read_array_header_2_0(fh)
        else:
            raise ValueError(f"Unsupported .npy version {(major, minor)}: {path}")
        offset = fh.tell()
    if fortran:
        raise ValueError(f"Fortran-order array unsupported for row reads: {path}")
    return (path, shape, dtype, offset)


def _read_npy_rows(meta, cols):
    """Read only the requested row indices (sorted) via seek without mmap accumulation."""
    path, shape, dtype, offset = meta
    n_cols = shape[1]
    row_bytes = n_cols * dtype.itemsize
    sorted_cols = sorted(int(c) for c in cols)
    out = np.empty((len(sorted_cols), n_cols), dtype=dtype)
    with open(path, "rb") as fh:
        for i, c in enumerate(sorted_cols):
            fh.seek(offset + c * row_bytes)
            out[i] = np.fromfile(fh, dtype=dtype, count=n_cols)
    return out


class MatrixStore:
    FUNC_PREFIX = {"progeny": "pw", "collectri": "tf", "renal_modules": "mod"}

    def __init__(self, store: Path = STORE):
        self.store = Path(store)
        self.is_lite = (self.store / "lite_manifest.json").exists()
        self.manifest = (json.loads((self.store / "lite_manifest.json").read_text())
                         if self.is_lite else None)

        self.genes = pd.read_parquet(self.store / "genes" / "gene_universe.parquet")
        cp_cols = (["matrix_row_idx", "pert_id", "pert_iname", "n_sigs", "kprl_lambda"]
                   if self.is_lite else None)
        self.cp_index = pd.read_parquet(self.store / "cp_index.parquet", columns=cp_cols)

        if self.is_lite:
            comp_cols = ["pert_id", "pert_iname", "inchikey", "inchikey14",
                         "matrix_row_idx", "n_sigs", "kprl_lambda"]
            self.compounds = pd.read_parquet(
                self.store / "chem" / "compounds.parquet", columns=comp_cols)
        else:
            self.compounds = pd.read_parquet(self.store / "chem" / "compounds.parquet")

        self.compounds["name_lower"] = (
            self.compounds["pert_iname"].fillna("").str.lower().str.strip()
        )
        hub_path = self.store / "annotations" / "repurposing_hub.parquet"
        if hub_path.exists():
            hub = pd.read_parquet(hub_path)
            cols = [c for c in ("pert_iname_lower", "clinical_phase", "moa",
                                "disease_area", "indication") if c in hub.columns]
            self.compounds = self.compounds.merge(
                hub[cols].drop_duplicates("pert_iname_lower"), how="left",
                left_on="name_lower", right_on="pert_iname_lower")
        diril_path = self.store / "annotations" / "nephrotoxicity_diril.parquet"
        if diril_path.exists():
            self.compounds = self.compounds.merge(
                pd.read_parquet(diril_path)[["pert_id", "diril_label", "match_method"]],
                on="pert_id", how="left")
        self.tdiki = pd.read_parquet(self.store / "matrices" / "tdiki_cp.parquet")
        if not self.is_lite:
            self.cp_index = self.cp_index.merge(self.tdiki, on="pert_id", how="left")
        self.compounds = self.compounds.merge(self.tdiki, on="pert_id", how="left")
        self.compounds = self.compounds.set_index("pert_id", drop=False)

        self._matrices = {}
        self._func = OrderedDict()
        self._ranks = None
        self._tau = OrderedDict()
        self._expr_cp = None
        self._mimic_cp = None
        self._alias = None
        self._expr = None
        self._targets = None
        self._genetic_index = None

        # Lite-mode lazy caches (strictly bounded)
        self._lite_active = {}
        self._lite_npy_meta = {}
        self._lite_indptr = {}
        self._lite_func = OrderedDict()
        self._lite_top_genes = None
        self._ecfp4_packed = None
        self._ecfp4_popcnt = None

    def matrix(self, context="kprl"):
        if self.is_lite:
            raise RuntimeError("full row-major matrix not shipped in lite mode")
        key = {"kprl": "kprl_cp_zscore", "pan": "pan_cp_zscore",
               "renal_epi": "renal_epi_cp_zscore", "renal_endo": "renal_endo_cp_zscore",
               "renal_immune": "renal_immune_cp_zscore"}[context]
        if key not in self._matrices:
            self._matrices[key] = np.load(self.store / "matrices" / f"{key}.npy",
                                          mmap_mode="r")
        return self._matrices[key]

    @property
    def ranks(self):
        if self.is_lite:
            raise RuntimeError("full row-major ranks not shipped in lite mode")
        if self._ranks is None:
            self._ranks = np.load(self.store / "matrices" / "kprl_ranks.npy",
                                  mmap_mode="r")
        return self._ranks

    @property
    def tau_tables(self):
        return self.tau_tables_for("kprl")

    def tau_tables_for(self, context="kprl"):
        if self.is_lite:
            ctx = "kprl_delta" if context == "kprl" else context
            if ctx in self._tau:
                self._tau.move_to_end(ctx)
                return self._tau[ctx]
            npz = np.load(self.lite_ctx_dir(ctx) / "tau_quantiles.npz")
            data = {k: npz[k] for k in npz.files}
            npz.close()
            self._tau[ctx] = data
            while len(self._tau) > 2:
                self._tau.popitem(last=False)
                trim_memory()
            return data
        if context not in self._tau:
            self._tau[context] = np.load(
                self.store / "matrices" / f"tau_null_tables_{context}.npz")
        return self._tau[context]

    # ---- Lite accessors ----
    def lite_ctx_dir(self, ctx: str) -> Path:
        return self.store / "matrices" / ctx

    def lite_active_idx(self, ctx: str) -> np.ndarray:
        if ctx not in self._lite_active:
            self._lite_active[ctx] = np.load(self.lite_ctx_dir(ctx) / "active_idx.npy")
        return self._lite_active[ctx]

    def _lite_meta(self, ctx: str, filename: str):
        key = (ctx, filename)
        if key not in self._lite_npy_meta:
            self._lite_npy_meta[key] = _parse_npy_header(self.lite_ctx_dir(ctx) / filename)
        return self._lite_npy_meta[key]

    def lite_read_ranks_cols(self, ctx: str, cols) -> np.ndarray:
        """Returns (n_active, len(cols)) uint16 without mmap page accumulation."""
        meta = self._lite_meta(ctx, "ranks_T.npy")
        return _read_npy_rows(meta, cols).T

    def lite_read_zhang_cols(self, ctx: str, cols) -> np.ndarray:
        """Returns (n_active, len(cols)) int8 without mmap page accumulation."""
        meta = self._lite_meta(ctx, "zhang_T.npy")
        return _read_npy_rows(meta, cols).T

    def lite_sum_xsum_cols(self, ctx: str, cols) -> np.ndarray:
        """Read sparse xsum_T gene rows and accumulate float32 sum over active rows."""
        if ctx not in self._lite_indptr:
            self._lite_indptr[ctx] = np.load(self.lite_ctx_dir(ctx) / "xsum_T_indptr.npy")
        indptr = self._lite_indptr[ctx]
        n_act = len(self.lite_active_idx(ctx))
        idx_meta = self._lite_meta(ctx, "xsum_T_indices.npy")
        dat_meta = self._lite_meta(ctx, "xsum_T_data.npy")
        idx_path, _, idx_dtype, idx_off = idx_meta
        dat_path, _, dat_dtype, dat_off = dat_meta
        idx_sz = idx_dtype.itemsize
        dat_sz = dat_dtype.itemsize
        acc = np.zeros(n_act, dtype=np.float32)
        sorted_cols = sorted(int(c) for c in cols)
        with open(idx_path, "rb") as fi, open(dat_path, "rb") as fd:
            for c in sorted_cols:
                s = int(indptr[c])
                e = int(indptr[c + 1])
                cnt = e - s
                if cnt <= 0:
                    continue
                fi.seek(idx_off + s * idx_sz)
                fd.seek(dat_off + s * dat_sz)
                row_idx = np.fromfile(fi, dtype=idx_dtype, count=cnt)
                row_val = np.fromfile(fd, dtype=dat_dtype, count=cnt).astype(np.float32)
                np.add.at(acc, row_idx, row_val)
        return acc

    def lite_func_block(self, ctx: str):
        """Bounded LRU (max 2 contexts: e.g. pan 31MB + kprl_delta 9MB) of float16 blocks."""
        if ctx in self._lite_func:
            self._lite_func.move_to_end(ctx)
            return self._lite_func[ctx]
        npz = np.load(self.lite_ctx_dir(ctx) / "func_blocks.npz")
        data = {k: npz[k] for k in npz.files}
        npz.close()
        self._lite_func[ctx] = data
        while len(self._lite_func) > 2:
            self._lite_func.popitem(last=False)
            trim_memory()
        return data

    def lite_top_genes(self):
        if self._lite_top_genes is None:
            npz = np.load(self.store / "matrices" / "compound_top_genes.npz")
            self._lite_top_genes = {k: npz[k] for k in npz.files}
            npz.close()
        return self._lite_top_genes

    def ecfp4_packed(self):
        if self._ecfp4_packed is None:
            self._ecfp4_packed = np.load(self.store / "chem" / "ecfp4_packed.npy")
            self._ecfp4_popcnt = np.load(self.store / "chem" / "ecfp4_popcnt.npy")
        return self._ecfp4_packed, self._ecfp4_popcnt

    def func_matrix(self, name, context="kprl"):
        key = (name, context)
        if key not in self._func:
            path = self.store / "matrices" / f"{name}_{context}.parquet"
            if not path.exists():
                path = self.store / "matrices" / f"{name}_cp.parquet"
            frame = pd.read_parquet(path).set_index("pert_id")
            prefix = self.FUNC_PREFIX[name]
            frame.columns = [f"{prefix}_{c}" for c in frame.columns]
            self._func[key] = frame
            while len(self._func) > 6:
                self._func.popitem(last=False)
                trim_memory()
        return self._func[key]

    @property
    def expr_kidney_cp(self):
        if self._expr_cp is None:
            self._expr_cp = pd.read_parquet(
                self.store / "matrices" / "expr_kidney_cp.parquet").set_index("pert_id")
        return self._expr_cp

    @property
    def genetic_mimicry_cp(self):
        if self._mimic_cp is None:
            self._mimic_cp = pd.read_parquet(
                self.store / "matrices" / "genetic_mimicry_cp.parquet").set_index("pert_id")
        return self._mimic_cp

    @property
    def aliases(self):
        if self._alias is None:
            path = self.store / "annotations" / "hgnc_aliases.parquet"
            if path.exists():
                alias = pd.read_parquet(path)
                self._alias = dict(zip(alias["alias_lower"], alias["entrez_id"]))
            else:
                self._alias = {}
        return self._alias

    @property
    def kidney_expression(self):
        if self._expr is None:
            frame = pd.read_parquet(self.store / "annotations" / "kidney_expression.parquet")
            self._expr = frame.set_index("entrez_id")
        return self._expr

    @property
    def fp_position(self):
        if not hasattr(self, "_fp_pos") or self._fp_pos is None:
            self._fp_pos = {pid: i for i, pid in enumerate(self.compounds["pert_id"])}
        return self._fp_pos

    def db(self):
        return sqlite3.connect(self.store / "nephroperturb.db", check_same_thread=False)

    # ---- resolution ----
    def resolve_genes(self, symbols):
        upper = {s.upper(): i for i, s in enumerate(self.genes["symbol"])}
        entrez_to_col = dict(zip(self.genes["entrez_id"], self.genes["matrix_col_idx"]))
        found, missing = [], []
        seen = set()
        for symbol in symbols:
            token = str(symbol).strip()
            if not token:
                continue
            col = upper.get(token.upper())
            if col is None and token.lower() in self.aliases:
                col = entrez_to_col.get(str(self.aliases[token.lower()]))
            if col is not None:
                if col not in seen:
                    seen.add(col)
                    found.append(col)
            else:
                missing.append(token)
        return found, missing

    def find_compound(self, token):
        token = str(token).strip()
        if token in self.compounds.index:
            row = self.compounds.loc[token]
            return row.iloc[0] if isinstance(row, pd.DataFrame) else row
        hit = self.compounds[self.compounds["inchikey"] == token.upper()]
        if len(hit):
            return hit.iloc[0]
        hit = self.compounds[self.compounds["inchikey14"] == token.upper()[:14]]
        if len(hit):
            return hit.iloc[0]
        hit = self.compounds[self.compounds["name_lower"] == token.lower()]
        if len(hit):
            return hit.iloc[0]
        return None

    def get_compound_detail(self, token):
        comp = self.find_compound(token)
        if comp is None:
            return None
        if not self.is_lite:
            return comp
        con = self.db()
        try:
            row = pd.read_sql("SELECT * FROM compounds WHERE pert_id = ?",
                              con, params=(comp["pert_id"],))
        finally:
            con.close()
        return row.iloc[0] if len(row) else comp

    def genetic_index_map(self):
        if self._genetic_index is None:
            self._genetic_index = pd.read_parquet(self.store / "genetic_index.parquet")
        return self._genetic_index


STORE_SINGLETON = None


def get_store():
    global STORE_SINGLETON
    if STORE_SINGLETON is None:
        STORE_SINGLETON = MatrixStore()
    return STORE_SINGLETON
