#!/usr/bin/env python
"""Build the Entrez-anchored gene universe and lookup tables (Tier-0)."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_settings, paths, phase_specs, read_tsv_gz, gctx_ids


def main():
    cfg = load_settings()
    lv = paths()["level5"]
    store = paths()["store"]
    out = store / "genes"
    out.mkdir(parents=True, exist_ok=True)

    frames = {}
    for phase, spec in phase_specs().items():
        gene = read_tsv_gz(lv / spec["gene"])
        gene["pr_gene_id"] = gene["pr_gene_id"].astype(str)
        frames[phase] = gene.set_index("pr_gene_id")

    ids = [set(f.index) for f in frames.values()]
    if not all(s == ids[0] for s in ids):
        raise SystemExit("phase gene universes differ")

    _, row_ids = gctx_ids(lv / phase_specs()["phase1"]["matrix"])
    first = next(iter(frames.values()))
    missing = [g for g in row_ids if g not in first.index]
    if missing:
        raise SystemExit(f"{len(missing)} gctx rows missing from gene_info")

    universe = first.loc[row_ids].reset_index()
    universe = universe.rename(columns={"pr_gene_id": "entrez_id"})
    universe["entrez_id"] = universe["entrez_id"].astype(str)
    universe["is_landmark"] = universe["pr_is_lm"].astype(int)
    universe["is_bing"] = universe["pr_is_bing"].astype(int)
    universe["matrix_col_idx"] = np.arange(len(universe))
    universe["symbol_lower"] = universe["pr_gene_symbol"].str.lower()
    keep = ["matrix_col_idx", "entrez_id", "pr_gene_symbol", "symbol_lower",
            "pr_gene_title", "is_landmark", "is_bing"]
    universe = universe[keep].rename(columns={"pr_gene_symbol": "symbol",
                                              "pr_gene_title": "title"})
    if universe["symbol"].duplicated().any():
        raise SystemExit("duplicate gene symbols in universe")

    aliases = pd.concat([
        universe[["entrez_id", "symbol"]].assign(alias=universe["symbol"]),
        universe[["entrez_id", "symbol"]].assign(alias=universe["symbol_lower"]),
    ])
    aliases["alias"] = aliases["alias"].str.lower()
    aliases = aliases.drop_duplicates(subset=["alias", "entrez_id"])

    universe.to_parquet(out / "gene_universe.parquet", index=False)
    aliases.to_parquet(out / "gene_aliases.parquet", index=False)
    np.save(store / "matrices" / "gene_ids.npy", universe["entrez_id"].to_numpy())

    n_lm = int(universe["is_landmark"].sum())
    n_bing = int(universe["is_bing"].sum())
    print(f"gene universe: {len(universe)} genes | landmark={n_lm} bing={n_bing} "
          f"other={len(universe) - n_bing}")
    print(f"wrote {out}/gene_universe.parquet")


if __name__ == "__main__":
    main()
