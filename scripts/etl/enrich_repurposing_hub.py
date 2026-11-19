"""Tier-1: Broad Drug Repurposing Hub -> clinical phase, MoA, targets, indications."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import OUT, ensure_dirs, fetch, write_meta

BASE = "https://s3.amazonaws.com/data.clue.io/repurposing/downloads/"
DRUGS = BASE + "repurposing_drugs_20200324.txt"
SAMPLES = BASE + "repurposing_samples_20200324.txt"


def main():
    ensure_dirs()
    drugs_path = fetch(DRUGS, "repurposing_drugs.txt")
    samples_path = fetch(SAMPLES, "repurposing_samples.txt")

    drugs = pd.read_csv(drugs_path, sep="\t", dtype=str, low_memory=False, skiprows=9)
    samples = pd.read_csv(samples_path, sep="\t", dtype=str, low_memory=False, skiprows=9)
    drugs.columns = [c.strip() for c in drugs.columns]
    samples.columns = [c.strip() for c in samples.columns]
    samples = samples.rename(columns={"InChIKey": "inchi_key", "Smiles": "smiles"})

    drugs["pert_iname_lower"] = drugs["pert_iname"].str.lower().str.strip()
    samples["pert_iname_lower"] = samples["pert_iname"].str.lower().str.strip()
    samples = samples.drop_duplicates("pert_iname_lower")

    keep = ["pert_iname_lower", "pert_iname"]
    for col in ("clinical_phase", "moa", "target", "disease_area", "indication"):
        if col in drugs.columns:
            keep.append(col)
    hub = drugs[keep].copy()
    for col in ("smiles", "inchi_key", "pubchem_cid"):
        if col in samples.columns:
            hub = hub.merge(samples[["pert_iname_lower", col]], on="pert_iname_lower", how="left")
    hub.to_parquet(OUT / "repurposing_hub.parquet", index=False)

    targets = drugs[["pert_iname_lower", "moa", "target"]].copy() \
        if "target" in drugs.columns else pd.DataFrame(columns=["pert_iname_lower", "moa", "target"])
    targets["target"] = targets["target"].fillna("")
    rows = []
    for _, row in targets.iterrows():
        for target in str(row["target"]).split("|"):
            target = target.strip()
            if target:
                rows.append({"pert_iname_lower": row["pert_iname_lower"],
                             "moa": row["moa"], "target_symbol": target})
    drug_targets = pd.DataFrame(rows).drop_duplicates()
    universe = pd.read_parquet(OUT.parent / "genes" / "gene_universe.parquet")
    symbol_map = dict(zip(universe["symbol"].str.upper(), universe["entrez_id"]))
    drug_targets["entrez_id"] = drug_targets["target_symbol"].str.upper().map(symbol_map)
    drug_targets.to_parquet(OUT / "drug_targets_hub.parquet", index=False)

    compounds = pd.read_parquet(OUT.parent / "chem" / "compounds.parquet")
    compounds["pert_iname_lower"] = compounds["pert_iname"].fillna("").str.lower().str.strip()
    matched = compounds["pert_iname_lower"].isin(set(hub["pert_iname_lower"]))
    print(f"[hub] drugs={len(hub)} targets={len(drug_targets)} "
          f"resolved_targets={int(drug_targets['entrez_id'].notna().sum())} "
          f"lincs_compounds_matched={int(matched.sum())}")
    write_meta("enrich_repurposing_hub",
               {"drugs": (DRUGS, drugs_path), "samples": (SAMPLES, samples_path)},
               notes=f"LINCS compounds matched by name: {int(matched.sum())}")


if __name__ == "__main__":
    main()
