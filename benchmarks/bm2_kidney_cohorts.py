#!/usr/bin/env python
"""BM-2: kidney cohort re-purposing recovery (demo signatures + Hub indications)."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))
from common import paths  # noqa: E402

OUT = ROOT / "benchmarks" / "outputs"
KEYWORDS = {
    "DKD": ["diabetes"],
    "LN": ["lupus"],
    "IgAN": ["iga nephropathy", "iga"],
    "AKI": ["acute kidney"],
    "CKD_fibrosis": ["chronic kidney", "fibrosis"],
    "FSGS": ["focal segmental", "fsgs"],
}


def percentile_ranks(ranking, positives):
    ordered = ranking.sort_values("renalconn", ascending=False).reset_index(drop=True)
    pct = pd.Series(np.arange(len(ordered)) / len(ordered), index=ordered["pert_id"])
    return pct


def main():
    from app.engine.scoring import rank_all
    OUT.mkdir(parents=True, exist_ok=True)
    store = paths()["store"]
    hub = pd.read_parquet(store / "annotations" / "repurposing_hub.parquet")
    compounds = pd.read_parquet(store / "chem" / "compounds.parquet")
    compounds["name_lower"] = compounds["pert_iname"].fillna("").str.lower().str.strip()
    merged = compounds.merge(hub[["pert_iname_lower", "indication"]],
                             left_on="name_lower", right_on="pert_iname_lower",
                             how="left")
    merged["indication"] = merged["indication"].fillna("").str.lower()

    cases = yaml.safe_load((ROOT / "config" / "renal_cases.yaml").read_text())["cases"]
    records = []
    per_case = {}
    for case_id, case in cases.items():
        positives = set(merged.loc[merged["indication"].str.contains(
            "|".join(KEYWORDS.get(case_id, [])), regex=True), "pert_id"])
        if not positives:
            print(f"[bm2] {case_id}: no indication-matched positives, skipped")
            continue
        row = {"case": case_id, "n_positives": len(positives)}
        for context in ("pan", "renal_epi", "kprl"):
            ranking = rank_all(case["up"], case["down"], context=context)
            pct = percentile_ranks(ranking, positives)
            vals = [float(pct.get(p, 1.0)) for p in positives]
            top_frac = np.mean([v <= 0.01 for v in vals])
            expected = len(positives) / len(ranking)
            row[f"{context}_median_pct"] = float(np.median(vals))
            row[f"{context}_fold_top1"] = float(top_frac / expected)
        records.append(row)
        per_case[case_id] = row
        print(f"[bm2] {case_id}: {row}")

    df = pd.DataFrame(records)
    summary = {}
    if len(df) >= 3:
        for context in ("pan", "renal_epi", "kprl"):
            summary[f"{context}_median_pct"] = float(df[f"{context}_median_pct"].mean())
        if {"pan_median_pct", "kprl_median_pct"}.issubset(df.columns):
            try:
                stat, p = wilcoxon(df["kprl_median_pct"], df["pan_median_pct"])
                summary["kprl_vs_pan_wilcoxon_p"] = float(p)
            except ValueError:
                summary["kprl_vs_pan_wilcoxon_p"] = None
    payload = {"cases": per_case, "summary": summary}
    (OUT / "bm2_kidney_cohorts.json").write_text(json.dumps(payload, indent=2))
    df.to_csv(OUT / "bm2_kidney_cohorts.csv", index=False)
    print(f"[bm2] {summary}")


if __name__ == "__main__":
    main()
