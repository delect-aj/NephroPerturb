"""Tier-1: FDA DIRIL 2024 nephrotoxicity gold labels -> LINCS compounds."""
import sys
from pathlib import Path

import openpyxl
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import OUT, RAW, ensure_dirs, fetch, write_meta

URL = "https://www.fda.gov/media/178824/download?attachment"

COLUMNS = {
    1: "pubchem_cid", 2: "drugbank_id", 3: "name", 4: "inchikey", 8: "smiles",
    15: "label_gong", 16: "label_shi", 17: "label_diril", 18: "fda_url",
    19: "atc_search_name", 20: "atc_code", 24: "notes",
}


def main():
    ensure_dirs()
    path = fetch(URL, "diril_dataset_508.xlsx", min_bytes=100_000)
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0 or row[3] in (None, ""):
            continue
        rec = {name: row[idx] for idx, name in COLUMNS.items()}
        label = str(rec["label_diril"] or "").strip().lower()
        rec["label"] = 1 if label.startswith("nephrotoxic") else 0
        rows.append(rec)
        if len(rows) > 400:
            break
    diril = pd.DataFrame(rows).drop_duplicates("name")
    diril["inchikey14"] = diril["inchikey"].fillna("").str.upper().str.slice(0, 14)
    diril["name_lower"] = diril["name"].str.lower().str.strip()
    diril["pubchem_cid"] = diril["pubchem_cid"].astype("Int64")
    diril.to_parquet(OUT / "diril.parquet", index=False)

    compounds = pd.read_parquet(OUT.parent / "chem" / "compounds.parquet")
    compounds["name_lower"] = compounds["pert_iname"].fillna("").str.lower().str.strip()
    by_key = compounds.merge(
        diril[["inchikey14", "label"]].dropna().drop_duplicates("inchikey14"),
        on="inchikey14", how="inner")
    by_name = compounds.merge(
        diril[["name_lower", "label"]].drop_duplicates("name_lower"),
        on="name_lower", how="inner")
    by_key["match_method"] = "inchikey14"
    by_name["match_method"] = "name"
    mapped = pd.concat([by_key, by_name])
    mapped = mapped.sort_values("match_method").drop_duplicates("pert_id")
    mapped = mapped[["pert_id", "label", "match_method"]].rename(
        columns={"label": "diril_label"})
    mapped["diril_source"] = "FDA_DIRIL_2024"
    mapped.to_parquet(OUT / "nephrotoxicity_diril.parquet", index=False)

    pos = int((diril["label"] == 1).sum())
    print(f"[diril] drugs={len(diril)} positive={pos} negative={len(diril) - pos} | "
          f"LINCS compounds mapped={len(mapped)} "
          f"(pos={int((mapped['diril_label'] == 1).sum())})")
    write_meta("enrich_diril_ctd", {"diril_xlsx": (URL, path)},
               notes="CTD/SIDER not ingested in this pass; DIRIL is the primary label source")


if __name__ == "__main__":
    main()
