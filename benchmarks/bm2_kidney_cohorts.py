#!/usr/bin/env python
"""BM-2 (v2): pre-registered re-purposing benchmark on QC-passed human kidney
biopsy cohorts.

Queries: cohort DEG signatures from scripts/etl/bm2_cohort_deg.py, gated by
config/bm2_cohorts_registry.yaml QC rules.

Positives (both reported, neither hidden):
  Tier-A  frozen clinical truth table (config/bm2_clinical_positives.yaml):
          guideline / high-evidence nephro-protective drugs per disease.
  Tier-B  Repurposing Hub indication keyword match (sensitivity analysis).

Six-level ladder (cohort- and study-level paired tests, Tier-A primary):
  1 unsplit500_pan          traditional unsplit 500-gene fgsea baseline
  2 pan_wtcs / pan_xsum / pan_zhang / pan_func   single kernels on Pan-Cell
  3 pan_ensemble            multi-scale fusion + empirical tau, Pan-Cell
  4 kprl_ensemble           fusion on K-PRL (kappa locked by BM-1, never tuned here)
  5 compartment_matched     context routed by disease/compartment
  6 statistics              cohort-level + study-level Wilcoxon, disease subgroups

Ranking universes: full compound library and InChIKey-14 scaffold-collapsed.

kappa and ensemble weights are fixed a priori by BM-1; nothing is tuned here.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))

OUT = ROOT / "benchmarks" / "outputs"
SIGS_PATH = OUT / "bm2_cohort_signatures.json"
POSITIVES_PATH = ROOT / "config" / "bm2_clinical_positives.yaml"
CONTEXT_POOL = ("pan", "renal_epi", "renal_immune")

INDICATION_KEYWORDS = {
    "DKD": r"\b(?:diabetes|diabetic)\b",
    "LN": r"\blupus\b",
    "CKD": r"\b(?:chronic kidney|ckd)\b",
    "AKI": r"\b(?:acute kidney|aki)\b",
    "IgAN": r"\biga nephropathy\b",
    "FSGS": r"\b(?:focal segmental|fsgs)\b",
}


def fold_enrichment(ordered_ids, positives, n_lib, top_frac=0.01):
    k = max(1, math.ceil(top_frac * n_lib))
    hits = sum(1 for pid in ordered_ids[:k] if pid in positives)
    expected = len(positives) * k / n_lib
    return (hits / expected if expected > 0 else 0.0), hits, k


def median_percentile(ordered_ids, positives, n_lib):
    pcts = {}
    for i, pid in enumerate(ordered_ids):
        if pid in positives:
            pcts[pid] = i / n_lib
    vals = sorted(pcts.get(p, 1.0) for p in positives)
    if not vals:
        return 1.0, {}
    m = len(vals)
    med = vals[m // 2] if m % 2 else (vals[m // 2 - 1] + vals[m // 2]) / 2
    return med, pcts


def recall_at(ordered_ids, positives, n_lib, frac):
    k = max(1, math.ceil(frac * n_lib))
    hits = sum(1 for pid in ordered_ids[:k] if pid in positives)
    return hits / len(positives) if positives else 0.0


def collapse_by_scaffold(ordered_ids, inchikey_of):
    seen, out = set(), []
    for pid in ordered_ids:
        key = inchikey_of.get(pid)
        if key in seen:
            continue
        seen.add(key)
        out.append(pid)
    return out


def route_contexts(disease, compartment):
    """Pre-registered compartment routing (plan section 3.3)."""
    c = (compartment or "").lower()
    if disease in ("LN", "IgAN", "FSGS"):
        return ["renal_immune", "renal_epi"]
    if "tubul" in c:
        return ["renal_epi"]
    if disease in ("AKI", "CKD"):
        return ["renal_epi"]
    return ["pan"]


def main():
    import numpy as np
    import pandas as pd
    import yaml
    from scipy.stats import wilcoxon
    from app.core.store import MatrixStore
    from app.engine import scoring
    from common import paths

    sigs = json.loads(SIGS_PATH.read_text())
    cohorts = {k: v for k, v in sigs["cohorts"].items() if v.get("passed")}
    if not cohorts:
        raise SystemExit("no QC-passed cohorts")
    print(f"[bm2] {len(cohorts)} QC-passed cohorts: {sorted(cohorts)}")

    store_path = paths()["store"]
    mstore = MatrixStore()
    hub = pd.read_parquet(store_path / "annotations" / "repurposing_hub.parquet")
    compounds = pd.read_parquet(store_path / "chem" / "compounds.parquet")
    compounds["name_lower"] = compounds["pert_iname"].fillna("").str.lower().str.strip()
    merged = compounds.merge(hub[["pert_iname_lower", "indication"]],
                              left_on="name_lower", right_on="pert_iname_lower", how="left")
    merged["indication"] = merged["indication"].fillna("").str.lower()
    in_lib = set(compounds["pert_id"])
    inchikey_of = dict(zip(compounds["pert_id"], compounds["inchikey14"]))

    tier_a_cfg = yaml.safe_load(POSITIVES_PATH.read_text())["tier_a"]
    name_to_pids = compounds.groupby("name_lower")["pert_id"].apply(list).to_dict()

    def positives_for(cid, disease, tier):
        if tier == "A":
            names = [d["name"].lower() for d in tier_a_cfg.get(disease, [])]
            pids = set()
            available = []
            for name in names:
                hit = set(name_to_pids.get(name, [])) & in_lib
                if hit:
                    available.append(name)
                    pids |= hit
            return pids, {"n_drugs_listed": len(names), "n_drugs_available": len(available),
                          "available": available}
        pattern = INDICATION_KEYWORDS.get(disease)
        if not pattern:
            return set(), {"n_drugs_available": 0}
        mask = merged["indication"].str.contains(pattern, regex=True)
        pids = set(merged.loc[mask, "pert_id"]) & in_lib
        return pids, {"n_drugs_listed": None, "n_drugs_available": len(pids)}

    def rankings_for(spec):
        """Compute ordered pid lists for every ladder rung."""
        up, down = spec["up"], spec["down"]
        rankings = {}
        if spec.get("top500_abs"):
            cols, _ = mstore.resolve_genes(spec["top500_abs"])
            ranks = scoring._ranks_for(mstore, "pan")
            es = scoring.signed_es(ranks, cols, ranks.shape[1])
            s = pd.Series(-es, index=mstore.cp_index["pert_id"].to_numpy())
            rankings["unsplit500_pan"] = s.sort_values(ascending=False).index.tolist()
        up_cols, dn_cols, _, _ = scoring._resolve(mstore, up, down, "all")
        kernels = {
            "pan_wtcs": lambda: scoring.wtcs_score(mstore, "pan", up_cols, dn_cols),
            "pan_xsum": lambda: scoring.xsum_extreme(mstore, "pan", up_cols, dn_cols),
            "pan_zhang": lambda: scoring.zhang_score(mstore, "pan", up_cols, dn_cols),
            "pan_func": lambda: scoring.func_scores(
                mstore, mstore.genes.iloc[up_cols]["symbol"].tolist(),
                mstore.genes.iloc[dn_cols]["symbol"].tolist(), "pan"),
        }
        for name, fn in kernels.items():
            s = pd.Series(fn(), index=mstore.cp_index["pert_id"].to_numpy())
            rankings[name] = s.sort_values(ascending=False).index.tolist()
        per_ctx = {}
        for ctx in ("pan", "renal_epi", "renal_immune", "kprl"):
            per_ctx[ctx] = scoring.rank_all(up, down, context=ctx)
        rankings["pan_ensemble"] = per_ctx["pan"].sort_values(
            "renalconn", ascending=False, kind="stable")["pert_id"].tolist()
        rankings["kprl_ensemble"] = per_ctx["kprl"].sort_values(
            "renalconn", ascending=False)["pert_id"].tolist()
        # compartment-matched: average renalconn over routed contexts
        score = None
        for ctx in route_contexts(spec["disease"], spec.get("compartment", "")):
            frame = per_ctx.get(ctx)
            if frame is None:
                frame = scoring.rank_all(up, down, context=ctx)
            vals = frame["renalconn"].to_numpy(dtype=np.float64)  # cp_index order
            score = vals if score is None else score + vals
        idx = mstore.cp_index["pert_id"].to_numpy()
        rankings["compartment_matched"] = pd.Series(score, index=idx).sort_values(
            ascending=False).index.tolist()
        return rankings

    methods = ("unsplit500_pan", "pan_wtcs", "pan_xsum", "pan_zhang", "pan_func",
               "pan_ensemble", "kprl_ensemble", "compartment_matched")
    rows, details = [], {}
    for cid, spec in cohorts.items():
        rankings = rankings_for(spec)
        for tier in ("A", "B"):
            positives, prov = positives_for(cid, spec["disease"], tier)
            if not positives:
                print(f"[bm2] {cid} tier {tier}: no positives, skipped")
                continue
            for mode in ("full", "scaffold"):
                for method in methods:
                    ordered = rankings[method]
                    if mode == "scaffold":
                        ordered = collapse_by_scaffold(ordered, inchikey_of)
                    n_lib = len(ordered)
                    med, pcts = median_percentile(ordered, positives, n_lib)
                    fold, hits, _ = fold_enrichment(ordered, positives, n_lib)
                    row = {"cohort": cid, "study_id": spec.get("study_id", spec["gse"]),
                           "disease": spec["disease"], "tier": tier, "mode": mode,
                           "method": method, "n_positives": len(positives),
                           "median_pct": round(med, 6), "fold_top1": round(fold, 4),
                           "hits_top1pct": hits,
                           "recall@1%": round(recall_at(ordered, positives, n_lib, 0.01), 6),
                           "recall@5%": round(recall_at(ordered, positives, n_lib, 0.05), 6),
                           "recall@10%": round(recall_at(ordered, positives, n_lib, 0.10), 6)}
                    rows.append(row)
                    if method == "kprl_ensemble" and tier == "A" and mode == "full":
                        details[cid] = {"positives_provenance": prov,
                                        "kprl_percentiles": {p: round(pcts.get(p, 1.0), 6)
                                                             for p in sorted(positives)}}
        print(f"[bm2] {cid} done ({spec['disease']}, study={spec.get('study_id')})")

    df = pd.DataFrame(rows)
    summary = {"n_cohorts": len(cohorts), "n_rows": len(df)}
    primary_mask = (df["tier"] == "A") & (df["mode"] == "full")
    prim = df[primary_mask]

    def paired_test(a, b, frame):
        aidx = frame[frame["method"] == a].set_index("cohort")["median_pct"]
        bidx = frame[frame["method"] == b].set_index("cohort")["median_pct"]
        both = pd.concat([aidx, bidx], axis=1, join="inner").dropna()
        if len(both) < 5:
            return None, len(both)
        try:
            _, p = wilcoxon(both.iloc[:, 0], both.iloc[:, 1])
            return float(p), len(both)
        except ValueError:
            return None, len(both)

    comparisons = [("kprl_ensemble", "pan_ensemble"), ("compartment_matched", "pan_ensemble"),
                   ("kprl_ensemble", "unsplit500_pan"), ("compartment_matched", "unsplit500_pan"),
                   ("kprl_ensemble", "pan_wtcs"), ("pan_ensemble", "unsplit500_pan"),
                   ("pan_ensemble", "pan_wtcs")]
    for tier, mode, tag in (("A", "full", "primary"), ("A", "scaffold", "tierA_scaffold"),
                            ("B", "full", "tierB")):
        frame = df[(df["tier"] == tier) & (df["mode"] == mode)]
        for a, b in comparisons:
            p, n = paired_test(a, b, frame)
            summary[f"{tag}_wilcoxon_p_{a}_vs_{b}"] = p
            summary[f"{tag}_n_{a}_vs_{b}"] = n
    # method means
    for tag, frame in (("tierA_full", prim),
                       ("tierB_full", df[(df["tier"] == "B") & (df["mode"] == "full")]),
                       ("tierA_scaffold", df[(df["tier"] == "A") & (df["mode"] == "scaffold")])):
        for method in methods:
            vals = frame[frame["method"] == method]["median_pct"]
            if len(vals):
                summary[f"{tag}_median_pct_mean_{method}"] = float(vals.mean())

    # study-level dedupe (mean over items per study, per method)
    for tag, frame in (("primary", prim), ("tierB", df[(df["tier"] == "B") & (df["mode"] == "full")])):
        per_study = frame.groupby(["study_id", "method"])["median_pct"].mean().unstack()
        summary[f"{tag}_n_studies"] = int(per_study.shape[0])
        for a, b in comparisons:
            if a in per_study.columns and b in per_study.columns and len(per_study) >= 5:
                pair = per_study[[a, b]].dropna()
                try:
                    _, p = wilcoxon(pair[a], pair[b])
                    summary[f"{tag}_study_level_wilcoxon_p_{a}_vs_{b}"] = float(p)
                except ValueError:
                    summary[f"{tag}_study_level_wilcoxon_p_{a}_vs_{b}"] = None

    # disease subgroup means (descriptive)
    for disease in sorted(prim["disease"].unique()):
        sub = prim[prim["disease"] == disease]
        summary.setdefault("disease_subgroups", {})[disease] = {
            m: float(sub[sub["method"] == m]["median_pct"].mean())
            for m in methods if len(sub[sub["method"] == m])}

    payload = {
        "design": {
            "cohorts": sorted(cohorts),
            "positives": {"tier_a": "frozen clinical truth table (bm2_clinical_positives.yaml)",
                          "tier_b": "Repurposing Hub indication keywords (sensitivity)"},
            "ladder": {
                "1": "unsplit500_pan", "2": "pan single kernels", "3": "pan_ensemble",
                "4": "kprl_ensemble (kappa locked by BM-1)",
                "5": "compartment_matched (pre-registered routing)",
                "6": "cohort-level + study-level Wilcoxon, disease subgroups"},
            "modes": ["full compound library", "InChIKey-14 scaffold-collapsed"],
            "primary": "kprl_ensemble vs pan_ensemble, Tier-A, full library, cohort-level",
            "caveats": "exact Wilcoxon on n cohorts; study-level dedupe reported; "
                       "ladder tests not multiplicity-corrected; routing fixed before run",
        },
        "summary": summary,
        "rows": rows,
        "details": details,
        "excluded_cohorts": sigs.get("excluded", {}),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "bm2_kidney_cohorts.json").write_text(json.dumps(payload, indent=2))
    df.to_csv(OUT / "bm2_kidney_cohorts.csv", index=False)
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
