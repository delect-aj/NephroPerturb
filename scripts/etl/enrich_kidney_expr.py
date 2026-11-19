"""Tier-1: GTEx kidney cortex/medulla and HPA kidney/cell-type expression."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import OUT, RAW, ensure_dirs, fetch, write_meta

GTEX_URL = ("https://storage.googleapis.com/adult-gtex/bulk-gex/v8/rna-seq/"
            "GTEx_Analysis_2017-06-05_v8_RNASeQCv1.1.9_gene_median_tpm.gct.gz")
RAW_GTEX = RAW / "gtex_median_tpm.gct.gz"
HPA_TISSUE_URL = "https://www.proteinatlas.org/download/tsv/rna_tissue_consensus.tsv.zip"
HPA_SC_URL = "https://www.proteinatlas.org/download/tsv/rna_single_cell_type.tsv.zip"

COMPARTMENTS = {
    "podocyte": {"podocytes"},
    "pt": {"proximal tubule cells"},
    "tal": {"loop of henle epithelial cells"},
    "dct": {"distal convoluted tubule cells", "renal connecting tubule cells"},
    "cd": {"renal collecting duct intercalated cells",
           "renal collecting duct principal cells"},
    "endo": {"vascular endothelial cells", "lymphatic endothelial cells"},
    "immune": {"macrophages", "t-cells", "b-cells"},
}


def main():
    ensure_dirs()
    universe = pd.read_parquet(OUT.parent / "genes" / "gene_universe.parquet")
    sym2entrez = dict(zip(universe["symbol"].str.upper(), universe["entrez_id"]))

    expr = None
    gtex = None
    gtex_path = RAW_GTEX
    if gtex_path.exists():
        try:
            gtex = pd.read_csv(gtex_path, sep="\t", skiprows=2, low_memory=False)
        except Exception as exc:  # partial/blocked download
            print(f"[warn] GTEx unusable ({exc}); falling back to HPA only")
            gtex = None
    if gtex is not None:
        gtex.columns = [c.strip() for c in gtex.columns]
        tissue_cols = [c for c in gtex.columns if c.startswith("Kidney")]
        gtex["entrez_id"] = gtex["Description"].str.upper().map(sym2entrez)
        gtex = gtex.dropna(subset=["entrez_id"]).drop_duplicates("entrez_id")
        expr = gtex[["entrez_id"] + tissue_cols].rename(columns={
            "Kidney - Cortex": "gtex_cortex_tpm", "Kidney - Medulla": "gtex_medulla_tpm"})
    else:
        expr = pd.DataFrame({"entrez_id": []})

    hpa_path = fetch(HPA_TISSUE_URL, "hpa_rna_tissue_consensus.tsv.zip", min_bytes=100_000)
    hpa = pd.read_csv(hpa_path, sep="\t", low_memory=False)
    hpa = hpa[hpa["Tissue"].str.lower() == "kidney"][["Gene name", "nTPM"]]
    hpa["entrez_id"] = hpa["Gene name"].str.upper().map(sym2entrez)
    hpa = hpa.dropna(subset=["entrez_id"]).drop_duplicates("entrez_id")
    expr = expr.merge(hpa.rename(columns={"nTPM": "hpa_kidney_ntpm"})[["entrez_id", "hpa_kidney_ntpm"]],
                      on="entrez_id", how="outer")

    sc_path = fetch(HPA_SC_URL, "hpa_rna_single_cell_type.tsv.zip", min_bytes=100_000)
    sc = pd.read_csv(sc_path, sep="\t", usecols=["Gene name", "Cell type", "nCPM"],
                     low_memory=False)
    sc["entrez_id"] = sc["Gene name"].str.upper().map(sym2entrez)
    sc = sc.dropna(subset=["entrez_id"])
    sc["Cell type"] = sc["Cell type"].str.lower().str.strip()
    for compartment, cell_types in COMPARTMENTS.items():
        sub = sc[sc["Cell type"].isin(cell_types)]
        if sub.empty:
            continue
        agg = sub.groupby("entrez_id")["nCPM"].mean().rename(f"sc_{compartment}")
        expr = expr.merge(agg, on="entrez_id", how="outer")

    expr.to_parquet(OUT / "kidney_expression.parquet", index=False)
    coverage = {
        "gtex": int(expr["gtex_cortex_tpm"].notna().sum()),
        "hpa_kidney": int(expr.get("hpa_kidney_ntpm", pd.Series(dtype=float)).notna().sum()),
        "sc_pt": int(expr.get("sc_pt", pd.Series(dtype=float)).notna().sum()),
    }
    sources = {"hpa_tissue": (HPA_TISSUE_URL, hpa_path),
               "hpa_single_cell": (HPA_SC_URL, sc_path)}
    if gtex is not None:
        sources["gtex"] = (GTEX_URL, gtex_path)
    print(f"[expr] genes={len(expr)} coverage={coverage}")
    write_meta("enrich_kidney_expr", sources,
               notes="compartments: " + ", ".join(COMPARTMENTS))


if __name__ == "__main__":
    main()
