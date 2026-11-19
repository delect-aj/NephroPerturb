#!/usr/bin/env python
"""Assemble the Tier-0 SQLite metadata database from build products."""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import paths


def main():
    store = paths()["store"]
    db = store / "nephroperturb.db"
    con = sqlite3.connect(db)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")

    genes = pd.read_parquet(store / "genes" / "gene_universe.parquet")
    genes.to_sql("genes", con, if_exists="replace", index=False,
                 method="multi", chunksize=5000)
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_genes_entrez ON genes(entrez_id)")
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_genes_symbol ON genes(symbol)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_genes_colidx ON genes(matrix_col_idx)")

    compounds = pd.read_parquet(store / "chem" / "compounds.parquet")
    compounds.to_sql("compounds", con, if_exists="replace", index=False,
                     method="multi", chunksize=2000)
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_cp_pert ON compounds(pert_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_cp_inchikey ON compounds(inchikey)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_cp_ik14 ON compounds(inchikey14)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_cp_row ON compounds(matrix_row_idx)")

    scaffolds = pd.read_parquet(store / "chem" / "scaffolds.parquet")
    scaffolds.to_sql("scaffolds", con, if_exists="replace", index=False,
                     method="multi", chunksize=5000)
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_scaffold_ik14 ON scaffolds(inchikey14)")

    genetic = pd.read_parquet(store / "genetic_index.parquet")
    genetic.to_sql("perturbations_genetic", con, if_exists="replace", index=False,
                   method="multi", chunksize=5000)
    con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_gen_pert ON perturbations_genetic(pert_id)")

    con.commit()
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("genes", "compounds", "scaffolds", "perturbations_genetic")}
    con.close()
    print(f"[db] {db} -> {counts}")


if __name__ == "__main__":
    main()
