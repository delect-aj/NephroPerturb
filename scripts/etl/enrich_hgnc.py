"""Tier-1: HGNC complete set -> symbol/Ensembl/alias normalization.

Primary source is the GCS TSV; when that host is unavailable the HGNC REST
`fetch/all` JSON endpoint is used as an equivalent mirror.
"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import OUT, RAW, ensure_dirs, fetch, write_meta

TSV_URL = "https://storage.googleapis.com/public-download-files/hgnc/tsv/tsv/hgnc_complete_set.txt"
JSON_URL = "https://rest.genenames.org/fetch/all"


def load_tsv(path):
    df = pd.read_csv(path, sep="\t", dtype=str, low_memory=False)
    return pd.DataFrame({
        "entrez_id": df["entrez_id"],
        "hgnc_id": df["hgnc_id"],
        "hgnc_symbol": df["symbol"],
        "ensembl_id": df["ensembl_gene_id"],
        "aliases": df.get("alias_symbol", "").fillna(""),
        "prev_symbols": df.get("prev_symbol", "").fillna(""),
        "status": df.get("status"),
    })


def load_json(path):
    docs = json.loads(Path(path).read_text())["response"]["docs"]
    rows = []
    for doc in docs:
        entrez = doc.get("entrez_id")
        if isinstance(entrez, list):
            entrez = entrez[0] if entrez else None
        rows.append({
            "entrez_id": str(entrez) if entrez else None,
            "hgnc_id": doc.get("hgnc_id"),
            "hgnc_symbol": doc.get("symbol"),
            "ensembl_id": doc.get("ensembl_gene_id"),
            "aliases": "|".join(doc.get("alias_symbol", []) or []),
            "prev_symbols": "|".join(doc.get("prev_symbol", []) or []),
            "status": doc.get("status"),
        })
    return pd.DataFrame(rows)


def main():
    ensure_dirs()
    tsv = RAW / "hgnc_complete_set.txt"
    js = RAW / "hgnc_complete_set.json"
    if tsv.exists() and tsv.stat().st_size > 1_000_000:
        frame, source = load_tsv(tsv), (TSV_URL, tsv)
    else:
        if not js.exists() or js.stat().st_size < 1_000_000:
            js = fetch(JSON_URL, "hgnc_complete_set.json", min_bytes=1_000_000)
        frame, source = load_json(js), (JSON_URL, js)

    frame = frame[frame["entrez_id"].notna()].copy()
    frame["entrez_id"] = frame["entrez_id"].astype(str).str.replace(r"\.0$", "", regex=True)
    frame = frame.drop_duplicates("entrez_id")
    frame.to_parquet(OUT / "hgnc.parquet", index=False)

    rows = []
    for _, row in frame.iterrows():
        for field, src in (("aliases", "alias"), ("prev_symbols", "prev")):
            for alias in str(row[field]).split("|"):
                alias = alias.strip()
                if alias:
                    rows.append({"alias_lower": alias.lower(),
                                 "entrez_id": row["entrez_id"], "source": src})
    aliases = pd.DataFrame(rows).drop_duplicates()
    aliases.to_parquet(OUT / "hgnc_aliases.parquet", index=False)

    universe = pd.read_parquet(OUT.parent / "genes" / "gene_universe.parquet")
    merged = universe.merge(frame, on="entrez_id", how="left")
    renamed = int((merged["hgnc_symbol"].notna() &
                   (merged["hgnc_symbol"] != merged["symbol"])).sum())
    print(f"[hgnc] {len(frame)} entrez ids | universe matched "
          f"{int(merged['hgnc_id'].notna().sum())}/{len(universe)} | "
          f"symbol renamed {renamed} | aliases {len(aliases)}")
    write_meta("enrich_hgnc", {"hgnc": source},
               notes=f"renamed symbols in LINCS universe: {renamed}")


if __name__ == "__main__":
    main()
