#!/usr/bin/env python
"""BM-3 (v2): T-DIKI v2 modality ablation and clinical-space safety filtering.

1) Modality ablation (5-fold GroupKFold by InChIKey-14):
   structure-only vs HA1E-tx-only (compounds with renal data) vs gated dual.
2) Safety interception on the Stage-2 QC-passed cohorts:
   clinical repositionable space (approved + phase I-III, scaffold-collapsed);
   Top-50 before vs after NephroSafe-ReRank (T-DIKI < 0.66);
   known nephrotoxic = DIRIL-positive OR clinical_diki_evidence flag.
3) Good-drug retention: Tier-A positives present in Top-50 before vs after.
4) Full-library high-risk / PAINS compression in Top-50.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))
from common import paths  # noqa: E402

OUT = ROOT / "benchmarks" / "outputs"
SIGS = OUT / "bm2_cohort_signatures.json"
POSITIVES = ROOT / "config" / "bm2_clinical_positives.yaml"
CLINICAL_PHASES = ("approved", "launched", "phase 3", "phase 2", "phase 1")
TDiki_TIER_CUTOFF = 0.66


def cv_scores(X, y, groups, weights, builder):
    oof = np.zeros(len(y))
    for tr, te in GroupKFold(n_splits=5).split(X, y, groups):
        m = builder()
        try:
            m.fit(X.iloc[tr], y[tr], sample_weight=weights[tr])
        except (TypeError, ValueError) as exc:
            if hasattr(m, "steps") and "sample_weight" in str(exc):
                m.fit(X.iloc[tr], y[tr],
                      **{f"{m.steps[-1][0]}__sample_weight": weights[tr]})
            elif "sample_weight" in str(exc):
                m.fit(X.iloc[tr], y[tr])
            else:
                raise
        oof[te] = m.predict_proba(X.iloc[te])[:, 1]
    return oof


def metrics(y, oof):
    return {"auroc": float(roc_auc_score(y, oof)),
            "auprc": float(average_precision_score(y, oof)),
            "brier": float(brier_score_loss(y, oof))}


def route_contexts(disease, compartment):
    c = (compartment or "").lower()
    if disease in ("LN", "IgAN", "FSGS"):
        return ["renal_immune", "renal_epi"]
    if "tubul" in c:
        return ["renal_epi"]
    if disease in ("AKI", "CKD"):
        return ["renal_epi"]
    return ["pan"]


def main():
    from app.core.store import MatrixStore
    from app.engine import scoring

    OUT.mkdir(parents=True, exist_ok=True)
    store_path = paths()["store"]
    mstore = MatrixStore()
    compounds = mstore.compounds.reset_index(drop=True).copy()
    compounds["pert_id"] = compounds["pert_id"].astype(str)
    labels = pd.read_parquet(store_path / "annotations" / "nephrotoxicity_diril.parquet")
    evidence_path = store_path / "annotations" / "clinical_diki_evidence.parquet"
    evidence = (pd.read_parquet(evidence_path) if evidence_path.exists()
                else pd.DataFrame(columns=["pert_id", "source", "renal_ae_flag"]))
    tdiki = pd.read_parquet(store_path / "matrices" / "tdiki_cp.parquet")
    metrics_cfg = json.loads((store_path / "models" / "tdiki_metrics.json").read_text())

    # -------- 1) modality ablation (own CV; structure vs tx on renal subset) --------
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.feature_selection import SelectKBest, f_classif

    def enet():
        return Pipeline([
            ("scale", StandardScaler()),
            ("select", SelectKBest(f_classif, k=200)),
            ("clf", LogisticRegression(penalty="elasticnet", solver="saga",
                                       l1_ratio=0.5, C=0.1, class_weight="balanced",
                                       max_iter=5000, random_state=0))])

    def l2():
        return Pipeline([("scale", StandardScaler()),
                         ("clf", LogisticRegression(penalty="l2", C=0.05,
                                                    class_weight="balanced",
                                                    max_iter=5000, random_state=0))])

    struct = pd.read_parquet(store_path / "chem" / "tdiki_v2_struct.parquet")
    cp_index = pd.read_parquet(store_path / "cp_index.parquet")
    renal_pids = set(cp_index.loc[cp_index["n_renal_sigs"] > 0, "pert_id"])

    def tx_frame():
        genes = pd.read_parquet(store_path / "genes" / "gene_universe.parquet")
        sym2col = {s.upper(): i for i, s in enumerate(genes["symbol"])}
        markers = ["HSPA1A", "DDIT3", "ATF4", "HSPA5", "HMOX1", "NQO1", "GCLM",
                   "HAVCR1", "LCN2", "SPP1", "VCAM1", "CASP1", "NLRP3", "IL1B",
                   "COL1A1", "FN1", "TGFB1", "HIF1A", "PPARA", "CPT1A"]
        cols = [sym2col[g] for g in markers if g in sym2col]
        names = [g for g in markers if g in sym2col]
        m = np.load(store_path / "matrices" / "renal_epi_cp_zscore.npy", mmap_mode="r")
        idx = cp_index[cp_index["n_renal_sigs"] > 0]
        marker = pd.DataFrame(np.asarray(m[idx["matrix_row_idx"].tolist()][:, cols]),
                              columns=[f"gex_{g}" for g in names],
                              index=idx["pert_id"].values)
        blocks = [marker]
        for name, prefix in (("progeny", "pw_"), ("renal_modules", "mod_")):
            f = pd.read_parquet(store_path / "matrices" / f"{name}_renal_epi.parquet")
            f = f.set_index("pert_id")
            f.columns = [prefix + str(c) for c in f.columns]
            blocks.append(f)
        tx = pd.concat(blocks, axis=1)
        tx["tas_renal"] = idx.set_index("pert_id")["tas_renal"].reindex(tx.index)
        return tx.fillna(0.0)

    tx = tx_frame()
    data = compounds[["pert_id", "inchikey14"]].merge(
        labels[["pert_id", "diril_label"]], on="pert_id").merge(
        struct, on="pert_id")
    groups = data["inchikey14"].astype("string").fillna("")
    groups = groups.where(groups.str.len() > 4, data["pert_id"].astype("string")).astype(str)
    wts = 1.0 / groups.map(groups.value_counts()).to_numpy()
    wts = wts / wts.mean()
    y = data["diril_label"].to_numpy()
    struct_cols = [c for c in struct.columns if c != "pert_id"]

    ablation = {"structure_only": metrics(y, cv_scores(
        data[struct_cols].fillna(0.0), y, groups, wts, enet))}
    tx_rows = data[data["pert_id"].isin(tx.index)].reset_index(drop=True)
    if len(tx_rows) >= 40 and tx_rows["diril_label"].nunique() == 2:
        tx_g = groups[data["pert_id"].isin(tx.index)].reset_index(drop=True)
        tx_w = wts[data["pert_id"].isin(tx.index)]
        y_tx = tx_rows["diril_label"].to_numpy()
        tx_cols = list(tx.columns)
        ablation["tx_only"] = {**metrics(y_tx, cv_scores(
            tx.reindex(tx_rows["pert_id"])[tx_cols].fillna(0.0),
            y_tx, tx_g, tx_w, l2)), "n": int(len(tx_rows))}
    ablation["gated_dual"] = {"oof_auroc": metrics_cfg.get("fused_oof_auroc"),
                              "mode": metrics_cfg.get("mode"),
                              "n": metrics_cfg.get("n_train")}
    print("[bm3] ablation", json.dumps(ablation, default=str))

    # -------- 2-4) safety interception on Stage-2 cohorts --------
    sigs = json.loads(SIGS.read_text())["cohorts"]
    cohorts = {k: v for k, v in sigs.items() if v.get("passed")}
    tier_cfg = yaml.safe_load(POSITIVES.read_text())["tier_a"]
    compounds["name_lower"] = compounds["pert_iname"].fillna("").str.lower().str.strip()
    name2pids = compounds.groupby("name_lower")["pert_id"].apply(list).to_dict()
    diril_pos = set(labels.loc[labels["diril_label"] == 1, "pert_id"])
    clinical_bad = set(evidence.loc[evidence["renal_ae_flag"] == 1, "pert_id"])
    known_bad = diril_pos | clinical_bad
    tdiki_prob = tdiki.set_index("pert_id")["tdiki_prob"]
    comp_idx = compounds.set_index("pert_id")
    pains = comp_idx["pains_alerts"].fillna(0).astype(int)
    inchikey = comp_idx["inchikey14"]
    phase = comp_idx["clinical_phase"].fillna("").str.lower()

    clinical_space = set(compounds.loc[
        phase.reindex(compounds["pert_id"]).str.contains("|".join(CLINICAL_PHASES))
        .to_numpy(), "pert_id"])
    print(f"[bm3] clinical space: {len(clinical_space)} compounds")

    def collapse(ordered, space=None):
        seen, out = set(), []
        for pid in ordered:
            if space is not None and pid not in space:
                continue
            key = inchikey.get(pid)
            if key in seen:
                continue
            seen.add(key)
            out.append(pid)
        return out

    rows = []
    for cid, spec in cohorts.items():
        score = None
        for ctx in route_contexts(spec["disease"], spec.get("compartment", "")):
            vals = scoring.rank_all(spec["up"], spec["down"], context=ctx)["renalconn"] \
                .to_numpy(dtype=np.float64)
            score = vals if score is None else score + vals
        ordered_all = pd.Series(score, index=mstore.cp_index["pert_id"].to_numpy()) \
            .sort_values(ascending=False).index.tolist()
        ordered = collapse(ordered_all, clinical_space)
        before = ordered[:50]
        filtered = [p for p in ordered if tdiki_prob.get(p, 0.5) < TDiki_TIER_CUTOFF]
        after = filtered[:50]

        good = set()
        for d in tier_cfg.get(spec["disease"], []):
            good |= set(name2pids.get(d["name"].lower(), []))
        bad_before = sum(1 for p in before if p in known_bad)
        bad_after = sum(1 for p in after if p in known_bad)
        good_before = sum(1 for p in before if p in good)
        good_after = sum(1 for p in after if p in good)
        high_before = sum(1 for p in before if tdiki_prob.get(p, 0.0) >= TDiki_TIER_CUTOFF)
        high_after = sum(1 for p in after if tdiki_prob.get(p, 0.0) >= TDiki_TIER_CUTOFF)
        pains_before = sum(1 for p in before if pains.get(p, 0) > 0)
        pains_after = sum(1 for p in after if pains.get(p, 0) > 0)
        row = {"cohort": cid, "disease": spec["disease"],
               "n_clinical_space": len(ordered),
               "top50_known_bad_before": bad_before, "top50_known_bad_after": bad_after,
               "bad_reduction": bad_before - bad_after,
               "bad_rate_before": round(bad_before / 50, 3),
               "bad_rate_after": round(bad_after / 50, 3),
               "tierA_good_before": good_before, "tierA_good_after": good_after,
               "tierA_retention": round(good_after / good_before, 3) if good_before else None,
               "high_tdiki_before": high_before, "high_tdiki_after": high_after,
               "pains_before": pains_before, "pains_after": pains_after,
               "list_kept": len(filtered)}
        rows.append(row)
        print(f"[bm3] {cid}: {row}")

    agg = {}
    if rows:
        df = pd.DataFrame(rows)
        agg = {c: float(df[c].mean()) for c in
               ("bad_rate_before", "bad_rate_after", "tierA_retention",
                "high_tdiki_before", "high_tdiki_after",
                "pains_before", "pains_after") if df[c].notna().any()}
        agg["n_cohorts"] = len(df)
        agg["bad_reduction_total"] = int(df["bad_reduction"].sum())

    payload = {"ablation": ablation, "safety": rows, "aggregate": agg,
               "clinical_space_size": len(clinical_space),
               "evidence_sources": sorted(evidence["source"].unique().tolist())
               if len(evidence) else [],
               "design": {
                   "cutoff": TDiki_TIER_CUTOFF,
                   "known_bad": "DIRIL-positive OR SIDER/CTD/FAERS renal AE evidence",
                   "space": "approved+launched+phase I-III, InChIKey-14 collapsed",
                   "retention": "Tier-A good drugs present in Top-50 after / before"}}
    (OUT / "bm3_diril_tdiki_cv.json").write_text(json.dumps(payload, indent=2))
    print("[bm3] wrote bm3_diril_tdiki_cv.json")


if __name__ == "__main__":
    main()
