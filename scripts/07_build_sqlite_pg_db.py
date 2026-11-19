#!/usr/bin/env python
"""Assemble the NephroPerturb SQLite metadata database from build products."""
import json
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, paths


def add_indexes(con):
    stmts = [
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_genes_entrez ON genes(entrez_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_genes_symbol ON genes(symbol)",
        "CREATE INDEX IF NOT EXISTS idx_genes_colidx ON genes(matrix_col_idx)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cp_pert ON compounds(pert_id)",
        "CREATE INDEX IF NOT EXISTS idx_cp_inchikey ON compounds(inchikey)",
        "CREATE INDEX IF NOT EXISTS idx_cp_ik14 ON compounds(inchikey14)",
        "CREATE INDEX IF NOT EXISTS idx_cp_row ON compounds(matrix_row_idx)",
        "CREATE INDEX IF NOT EXISTS idx_cp_phase ON compounds(clinical_phase)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_scaffold_ik14 ON scaffolds(inchikey14)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_gen_pert ON perturbations_genetic(pert_id)",
        "CREATE INDEX IF NOT EXISTS idx_target_pert ON drug_targets(pert_id)",
        "CREATE INDEX IF NOT EXISTS idx_target_gene ON drug_targets(entrez_id)",
        "CREATE INDEX IF NOT EXISTS idx_nexpr_gene ON kidney_expression(entrez_id)",
        "CREATE INDEX IF NOT EXISTS idx_cases_disease ON renal_case_studies(disease_name)",
    ]
    for stmt in stmts:
        con.execute(stmt)


def build_cases(store):
    with open(ROOT / "config" / "renal_cases.yaml") as fh:
        cases = yaml.safe_load(fh)["cases"]
    rows = []
    for case_id, c in cases.items():
        rows.append({
            "case_id": case_id,
            "disease_name": c["disease_name"],
            "compartment": c["compartment"],
            "dataset_accession": c.get("dataset_accession"),
            "pmid": c.get("pmid"),
            "up_genes_json": json.dumps(c["up"]),
            "down_genes_json": json.dumps(c["down"]),
        })
    return pd.DataFrame(rows)


def main():
    store = paths()["store"]
    ann = store / "annotations"
    db = store / "nephroperturb.db"
    con = sqlite3.connect(db)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")

    genes = pd.read_parquet(store / "genes" / "gene_universe.parquet")
    hgnc_path = ann / "hgnc.parquet"
    if hgnc_path.exists():
        hgnc = pd.read_parquet(hgnc_path)[
            ["entrez_id", "hgnc_id", "hgnc_symbol", "ensembl_id", "aliases"]]
        genes = genes.merge(hgnc, on="entrez_id", how="left")
    genes.to_sql("genes", con, if_exists="replace", index=False,
                 method="multi", chunksize=5000)

    compounds = pd.read_parquet(store / "chem" / "compounds.parquet")
    compounds["data_release"] = "L1000_Phase1_2"
    compounds["pert_iname_lower"] = compounds["pert_iname"].fillna("").str.lower().str.strip()
    diril_full = None
    diril_path = ann / "diril.parquet"
    if diril_path.exists():
        diril_full = pd.read_parquet(diril_path)
        db_cols = [c for c in ("inchikey14", "drugbank_id", "atc_code") if c in diril_full.columns]
        compounds = compounds.merge(
            diril_full[db_cols].dropna(subset=["inchikey14"]).drop_duplicates("inchikey14"),
            on="inchikey14", how="left", suffixes=("", "_diril"))
    hub_path = ann / "repurposing_hub.parquet"
    if hub_path.exists():
        hub = pd.read_parquet(hub_path)
        cols = [c for c in ("pert_iname_lower", "clinical_phase", "moa", "target",
                            "disease_area", "indication") if c in hub.columns]
        compounds = compounds.merge(hub[cols].drop_duplicates("pert_iname_lower"),
                                    on="pert_iname_lower", how="left")
    diril_path = ann / "nephrotoxicity_diril.parquet"
    if diril_path.exists():
        compounds = compounds.merge(
            pd.read_parquet(diril_path)[["pert_id", "diril_label", "match_method"]],
            on="pert_id", how="left")
    tdiki_path = store / "matrices" / "tdiki_cp.parquet"
    if tdiki_path.exists():
        compounds = compounds.merge(
            pd.read_parquet(tdiki_path)[["pert_id", "tdiki_prob", "tdiki_tier"]],
            on="pert_id", how="left")
    compounds.to_sql("compounds", con, if_exists="replace", index=False,
                     method="multi", chunksize=2000)

    if "tdiki_prob" in compounds.columns:
        compounds["diril_source"] = compounds["diril_label"].map(
            lambda v: "FDA_DIRIL_2024" if pd.notna(v) else None)
        nephro = compounds[["pert_id", "diril_label", "diril_source",
                            "tdiki_prob", "tdiki_tier"]] \
            if "match_method" not in compounds.columns else \
            compounds[["pert_id", "diril_label", "diril_source", "tdiki_prob",
                       "tdiki_tier", "match_method"]]
        nephro = nephro.rename(columns={"match_method": "diril_match"})
        nephro.to_sql("nephrotoxicity", con, if_exists="replace", index=False,
                      method="multi", chunksize=2000)

    scaffolds = pd.read_parquet(store / "chem" / "scaffolds.parquet")
    phase_rank = {"launched": 5, "approved": 5, "phase 4": 4, "phase 3": 3,
                  "phase 2": 2, "phase 1": 1, "preclinical": 0}
    rank_label = {v: k for k, v in phase_rank.items()}
    if "clinical_phase" in compounds.columns:
        tmp = compounds.dropna(subset=["inchikey14"]).copy()
        tmp["phase_rank"] = tmp["clinical_phase"].fillna("").str.lower().map(phase_rank)
        best = tmp.groupby("inchikey14")["phase_rank"].max()
        scaffolds["highest_phase"] = scaffolds["inchikey14"].map(best).map(rank_label)
    if "diril_label" in compounds.columns:
        tmp = compounds.dropna(subset=["inchikey14"])
        def consensus(values):
            if (values == 1).any():
                return "positive"
            if (values == 0).any():
                return "negative"
            return None
        scaffolds["diril_consensus"] = scaffolds["inchikey14"].map(
            tmp.groupby("inchikey14")["diril_label"].agg(consensus))
    scaffolds.to_sql("scaffolds", con, if_exists="replace", index=False,
                     method="multi", chunksize=5000)

    genetic = pd.read_parquet(store / "genetic_index.parquet")
    genetic["target_symbol"] = genetic["pert_iname"].fillna("").str.upper()
    entrez_map = dict(zip(genes["symbol"].str.upper(), genes["entrez_id"]))
    genetic["target_entrez_id"] = genetic["target_symbol"].map(entrez_map)
    crispr_path = paths()["data"] / "LINCS_L1000_CRISPR_KO_Consensus_Sigs.gmt"
    if crispr_path.exists():
        crispr_genes = set()
        with open(crispr_path) as fh:
            for line in fh:
                name = line.split("\t", 1)[0].upper()
                crispr_genes.add(name.rsplit("_", 1)[0])
        genetic["has_crispr_consensus"] = genetic["target_symbol"].isin(crispr_genes)
    genetic.to_sql("perturbations_genetic", con, if_exists="replace", index=False,
                   method="multi", chunksize=5000)

    targets_path = ann / "drug_targets_hub.parquet"
    if targets_path.exists():
        targets = pd.read_parquet(targets_path)
        name2pert = (compounds[["pert_iname_lower", "pert_id"]]
                     .drop_duplicates("pert_iname_lower"))
        targets = targets.merge(name2pert, on="pert_iname_lower", how="inner")
        targets = targets[["pert_id", "target_symbol", "entrez_id", "moa"]].drop_duplicates()
        targets.to_sql("drug_targets", con, if_exists="replace", index=False,
                       method="multi", chunksize=5000)

    expr_path = ann / "kidney_expression.parquet"
    if expr_path.exists():
        expr = pd.read_parquet(expr_path)
        expr.to_sql("kidney_expression", con, if_exists="replace", index=False,
                    method="multi", chunksize=5000)

    cases = build_cases(store)
    cases.to_sql("renal_case_studies", con, if_exists="replace", index=False)

    con.execute("""CREATE TABLE IF NOT EXISTS job_provenance (
        job_id TEXT PRIMARY KEY, created_at TEXT, query_modality TEXT, sop_id TEXT,
        params_json TEXT, input_hash TEXT, result_summary_json TEXT, llm_used INTEGER)""")

    add_indexes(con)
    con.commit()
    counts = {}
    for table in ("genes", "compounds", "scaffolds", "perturbations_genetic",
                  "drug_targets", "kidney_expression", "renal_case_studies"):
        counts[table] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    con.close()
    print(f"[db] {db} -> {counts}")


if __name__ == "__main__":
    main()
