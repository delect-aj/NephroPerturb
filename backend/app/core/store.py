"""Lazy loaders for matrices, annotations and the SQLite metadata database."""
import os
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

STORE = Path(os.environ.get("NEPHRO_STORE", "/public/home/dongb/agent/renalkb/store"))
CONFIG = Path(os.environ.get("NEPHRO_CONFIG", "/public/home/dongb/agent/renalkb/config"))


class MatrixStore:
    def __init__(self, store: Path = STORE):
        self.store = store
        self.genes = pd.read_parquet(store / "genes" / "gene_universe.parquet")
        self.cp_index = pd.read_parquet(store / "cp_index.parquet")
        self.compounds = pd.read_parquet(store / "chem" / "compounds.parquet")
        self.compounds["name_lower"] = self.compounds["pert_iname"].fillna("").str.lower().str.strip()
        hub_path = store / "annotations" / "repurposing_hub.parquet"
        if hub_path.exists():
            hub = pd.read_parquet(hub_path)
            cols = [c for c in ("pert_iname_lower", "clinical_phase", "moa",
                                "disease_area", "indication") if c in hub.columns]
            self.compounds = self.compounds.merge(
                hub[cols].drop_duplicates("pert_iname_lower"), how="left",
                left_on="name_lower", right_on="pert_iname_lower")
        diril_path = store / "annotations" / "nephrotoxicity_diril.parquet"
        if diril_path.exists():
            self.compounds = self.compounds.merge(
                pd.read_parquet(diril_path)[["pert_id", "diril_label", "match_method"]],
                on="pert_id", how="left")
        self.tdiki = pd.read_parquet(store / "matrices" / "tdiki_cp.parquet")
        self.cp_index = self.cp_index.merge(self.tdiki, on="pert_id", how="left")
        self.compounds = self.compounds.merge(self.tdiki, on="pert_id", how="left")
        self.compounds = self.compounds.set_index("pert_id", drop=False)
        self._matrices = {}
        self._func = {}
        self._ranks = None
        self._tau = None
        self._alias = None
        self._expr = None
        self._targets = None
        self._genetic_index = None

    def matrix(self, context="kprl"):
        key = {"kprl": "kprl_cp_zscore", "pan": "pan_cp_zscore",
               "renal_epi": "renal_epi_cp_zscore", "renal_endo": "renal_endo_cp_zscore",
               "renal_immune": "renal_immune_cp_zscore"}[context]
        if key not in self._matrices:
            self._matrices[key] = np.load(self.store / "matrices" / f"{key}.npy",
                                          mmap_mode="r")
        return self._matrices[key]

    @property
    def ranks(self):
        if self._ranks is None:
            self._ranks = np.load(self.store / "matrices" / "kprl_ranks.npy",
                                  mmap_mode="r")
        return self._ranks

    @property
    def tau_tables(self):
        if self._tau is None:
            self._tau = np.load(self.store / "matrices" / "tau_null_tables.npz")
        return self._tau

    def func_matrix(self, name):
        if name not in self._func:
            frame = pd.read_parquet(self.store / "matrices" / f"{name}_cp.parquet")
            frame = frame.set_index("pert_id")
            prefix = {"progeny": "pw", "collectri": "tf", "renal_modules": "mod"}[name]
            frame.columns = [f"{prefix}_{c}" for c in frame.columns]
            self._func[name] = frame
        return self._func[name]

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
        """Row position in ecfp4_cp.npy (compounds.parquet order)."""
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
        for symbol in symbols:
            token = str(symbol).strip()
            col = upper.get(token.upper())
            if col is None and token in self.aliases:
                col = entrez_to_col.get(str(self.aliases[token]))
            (found if col is not None else missing).append(col if col is not None else token)
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
