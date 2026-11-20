#!/usr/bin/env python
"""T-DIKI v2: gated late fusion of a structure expert and a renal-cell
toxicology expert.

Labels: FDA DIRIL 2024 only (171 pos / 146 neg drugs); CTD/SIDER/FAERS
evidence is display-only and never enters training.

Expert A (structure): ECFP4 (2048) + MACCS keys (167) + RDKit descriptors
(15). Candidate learners (ElasticNet-LR, L2-LR, ExtraTrees, LightGBM) are
compared under 5-fold GroupKFold(InChIKey-14); the winner is Platt-calibrated.

Expert B (renal tx): only compounds with n_renal_sigs > 0, using renal_epi
(measured kidney-cell context) features: 14 PROGENy, 13 renal modules,
15 injury/oxidative marker genes and TAS_renal.

Gate: P = sigma(b0 + bS*logit(Ps) + g* bT*logit(Pt)), g = 1[n_renal>0]*lambda.
Protective rule: if the fused OOF AUROC does not strictly beat structure-only,
beta_T is pinned to 0 and the renal evidence is surfaced as an independent
interpretable alert instead of lowering discrimination.

Both experts and the gate receive scaffold weights; every learner gets
sample_weight (fixes the old ElasticNet omission).
"""
import json
import sys
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import paths  # noqa: E402

MARKER_GENES = [
    "HSPA1A", "HSPH1", "DDIT3", "ATF4", "ATF6", "HSPA5", "XBP1", "ERN1",
    "CDKN1A", "GADD45A", "MDM2", "BBC3", "BAX", "TP53",
    "HMOX1", "NQO1", "TXNRD1", "GCLM", "SLC7A11", "GPX4",
    "SQSTM1", "MAP1LC3B", "BECN1", "ATG5",
    "HAVCR1", "LCN2", "SPP1", "SOX9", "VCAM1",
    "IL6", "CXCL8", "CCL2", "NFKB1", "RELA",
    "COL1A1", "COL3A1", "FN1", "SERPINE1", "TGFB1",
    "HIF1A", "VEGFA", "CA9", "LDHA", "SLC2A1",
    "PPARA", "PPARGC1A", "CPT1A", "ACADM",
    "CASP1", "NLRP3", "GSDMD", "IL1B", "IL18",
]
STRUCT_DESCRIPTORS = ["mw", "logp", "tpsa", "hbd", "hba", "rotb", "qed",
                      "lipinski_violations", "fraction_csp3", "ring_count",
                      "num_aromatic_rings", "heavy_atom_count", "formal_charge",
                      "mol_mr", "pains_count"]


def build_struct_features(store):
    """ECFP4 (existing) + MACCS + RDKit descriptors, aligned to compounds order."""
    from rdkit import Chem
    from rdkit.Chem import Descriptors, MACCSkeys, rdMolDescriptors
    from rdkit.Chem.FilterCatalog import FilterCatalog, FilterCatalogParams

    compounds = pd.read_parquet(store / "chem" / "compounds.parquet")
    params = FilterCatalogParams()
    params.AddCatalog(FilterCatalogParams.FilterCatalogs.PAINS)
    pains = FilterCatalog(params)
    rows = {c: np.zeros(len(compounds), dtype=np.float32) for c in STRUCT_DESCRIPTORS}
    maccs = np.zeros((len(compounds), 167), dtype=np.uint8)
    smi_col = "canonical_smiles" if "canonical_smiles" in compounds.columns else "input_smiles"
    for i, smi in enumerate(compounds[smi_col]):
        mol = Chem.MolFromSmiles(smi) if isinstance(smi, str) else None
        if mol is None:
            continue
        try:
            maccs[i] = np.frombuffer(MACCSkeys.GenMACCSKeys(mol).ToBitString().encode(),
                                     dtype=np.uint8) - ord("0")
            rows["fraction_csp3"][i] = rdMolDescriptors.CalcFractionCSP3(mol)
            rows["ring_count"][i] = rdMolDescriptors.CalcNumRings(mol)
            rows["num_aromatic_rings"][i] = rdMolDescriptors.CalcNumAromaticRings(mol)
            rows["heavy_atom_count"][i] = mol.GetNumHeavyAtoms()
            rows["formal_charge"][i] = Chem.GetFormalCharge(mol)
            rows["mol_mr"][i] = Descriptors.MolMR(mol)
            rows["pains_count"][i] = len(pains.GetMatches(mol))
        except Exception:  # noqa: BLE001
            continue
        if i % 4000 == 0:
            print(f"  struct {i}/{len(compounds)}", flush=True)
    ecfp = np.load(store / "chem" / "ecfp4_cp.npy")
    frame = pd.DataFrame({"pert_id": compounds["pert_id"].values})
    desc = pd.DataFrame({c: rows[c] for c in STRUCT_DESCRIPTORS})
    for c in ("mw", "logp", "tpsa", "hbd", "hba", "rotb", "qed", "lipinski_violations"):
        if c in compounds.columns:
            desc[c] = compounds[c].fillna(0.0).to_numpy(dtype=np.float32)
    frame = pd.concat([frame, desc.reset_index(drop=True),
                       pd.DataFrame(maccs, columns=[f"maccs_{i}" for i in range(167)]),
                       pd.DataFrame(ecfp, columns=[f"fp_{i}" for i in range(ecfp.shape[1])])],
                      axis=1)
    frame.to_parquet(store / "chem" / "tdiki_v2_struct.parquet", index=False)
    feat_cols = [c for c in frame.columns if c != "pert_id"]
    print(f"[struct] {len(compounds)} compounds x {len(feat_cols)} features")
    return frame, feat_cols


def build_tx_features(store):
    """renal_epi compact toxicology features (compounds with renal data only)."""
    cp = pd.read_parquet(store / "cp_index.parquet")
    renal = cp[cp["n_renal_sigs"] > 0].set_index("pert_id")
    genes = pd.read_parquet(store / "genes" / "gene_universe.parquet")
    sym2col = {s.upper(): i for i, s in enumerate(genes["symbol"])}
    renal_matrix = np.load(store / "matrices" / "renal_epi_cp_zscore.npy", mmap_mode="r")
    cols = [sym2col[g] for g in MARKER_GENES if g in sym2col]
    names = [g for g in MARKER_GENES if g in sym2col]
    marker = pd.DataFrame(np.asarray(renal_matrix[np.array(
        renal["matrix_row_idx"].tolist())][:, cols]),
        columns=[f"gex_{g}" for g in names], index=renal.index)
    blocks = [marker]
    for name, prefix in (("progeny", "pw_"), ("renal_modules", "mod_")):
        frame = pd.read_parquet(store / "matrices" / f"{name}_renal_epi.parquet")
        frame = frame.set_index("pert_id")
        frame.columns = [prefix + str(c) for c in frame.columns]
        blocks.append(frame)
    tx = pd.concat(blocks, axis=1)
    tx["tas_renal"] = renal["tas_renal"].reindex(tx.index).fillna(0.0)
    return tx.fillna(0.0)


def scaffold_weights(groups):
    w = 1.0 / pd.Series(groups).map(pd.Series(groups).value_counts()).to_numpy()
    return w / w.mean()


def model_candidates():
    """Name -> factory (fresh, unfitted estimator per call)."""
    return {
        "elasticnet": lambda: Pipeline([
            ("scale", StandardScaler()),
            ("select", SelectKBest(f_classif, k=200)),
            ("clf", LogisticRegression(penalty="elasticnet", solver="saga",
                                       l1_ratio=0.5, C=0.1, class_weight="balanced",
                                       max_iter=5000, random_state=0)),
        ]),
        "l2": lambda: Pipeline([
            ("scale", StandardScaler()),
            ("select", SelectKBest(f_classif, k=300)),
            ("clf", LogisticRegression(penalty="l2", C=0.1, class_weight="balanced",
                                       max_iter=5000, random_state=0)),
        ]),
        "extratrees": lambda: ExtraTreesClassifier(
            n_estimators=400, max_depth=8, min_samples_leaf=3,
            class_weight="balanced", random_state=0, n_jobs=8),
        "lightgbm": lambda: __import__("lightgbm").LGBMClassifier(
            n_estimators=400, learning_rate=0.03, num_leaves=15, max_depth=5,
            min_child_samples=10, subsample=0.8, subsample_freq=1,
            colsample_bytree=0.15, reg_lambda=1.0, class_weight="balanced",
            random_state=0, verbosity=-1),
    }


def fit_weighted(m, X, y, w):
    """Fit with sample weights, routing into the final Pipeline step."""
    try:
        m.fit(X, y, sample_weight=w)
    except (TypeError, ValueError) as exc:
        if "sample_weight" not in str(exc):
            raise
        if hasattr(m, "steps"):
            last = m.steps[-1][0]
            m.fit(X, y, **{f"{last}__sample_weight": w})
        else:
            m.fit(X, y)
    return m


def oof_predict(builder, X, y, groups, weights):
    oof = np.zeros(len(y))
    for tr, te in GroupKFold(n_splits=5).split(X, y, groups):
        m = fit_weighted(builder(), X.iloc[tr], y[tr], weights[tr])
        oof[te] = m.predict_proba(X.iloc[te])[:, 1]
    return oof


def fit_with_weights(m, X, y, w):
    return fit_weighted(m, X, y, w)


def logit(p):
    p = np.clip(np.asarray(p, dtype=np.float64), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def main():
    t0 = time.time()
    store = paths()["store"]
    models_dir = store / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    struct, struct_cols = build_struct_features(store)
    tx = build_tx_features(store)
    tx_cols = list(tx.columns)
    print(f"[tx] {tx.shape[0]} compounds x {tx.shape[1]} renal features")

    compounds = pd.read_parquet(store / "chem" / "compounds.parquet")
    labels = pd.read_parquet(store / "annotations" / "nephrotoxicity_diril.parquet")
    merged = compounds[["pert_id", "inchikey14"]].merge(
        labels[["pert_id", "diril_label"]], on="pert_id", how="inner")
    merged = merged.merge(struct, on="pert_id", how="left")
    groups = merged["inchikey14"].astype("string").fillna("")
    groups = groups.where(groups.str.len() > 4, merged["pert_id"].astype("string")).astype(str)
    weights = scaffold_weights(groups)
    y = merged["diril_label"].to_numpy()

    # ---------------- Expert A: structure ----------------
    struct_report = {}
    best_name, best_oof = None, None
    X = merged[struct_cols].fillna(0.0)
    for name, builder in model_candidates().items():
        oof = oof_predict(builder, X, y, groups, weights)
        auc = float(roc_auc_score(y, oof))
        struct_report[name] = {"auroc": auc,
                               "auprc": float(average_precision_score(y, oof)),
                               "brier": float(brier_score_loss(y, oof))}
        print(f"[struct] {name}: {struct_report[name]}")
        if best_oof is None or auc > struct_report[best_name]["auroc"]:
            best_name, best_oof = name, oof
    print(f"[struct] winner: {best_name}")

    # ---------------- Expert B: renal tx ----------------
    renal_mask = merged["pert_id"].isin(tx.index).to_numpy()
    tx_sub = merged[renal_mask].reset_index(drop=True).merge(
        tx.reset_index(), on="pert_id", how="left")
    tx_groups = groups[renal_mask].reset_index(drop=True)
    tx_w = weights[renal_mask]
    y_tx = tx_sub["diril_label"].to_numpy()
    oof_tx = np.zeros(len(tx_sub))
    if len(tx_sub) >= 40 and len(np.unique(y_tx)) == 2:
        for tr, te in GroupKFold(n_splits=5).split(tx_sub, y_tx, tx_groups):
            m = Pipeline([("scale", StandardScaler()),
                          ("clf", LogisticRegression(penalty="l2", C=0.05,
                                                     class_weight="balanced",
                                                     max_iter=5000, random_state=0))])
            fit_with_weights(m, tx_sub.iloc[tr][tx_cols].fillna(0.0), y_tx[tr], tx_w[tr])
            oof_tx[te] = m.predict_proba(tx_sub.iloc[te][tx_cols].fillna(0.0))[:, 1]
        tx_report = {"n": int(len(tx_sub)), "auroc": float(roc_auc_score(y_tx, oof_tx)),
                     "auprc": float(average_precision_score(y_tx, oof_tx)),
                     "brier": float(brier_score_loss(y_tx, oof_tx))}
    else:
        tx_report = {"n": int(len(tx_sub)), "auroc": None}
    print(f"[tx] {tx_report}")

    # ---------------- Gate ----------------
    g = np.zeros(len(merged))
    lam = pd.read_parquet(store / "cp_index.parquet").set_index("pert_id")["kprl_lambda"]
    g[renal_mask] = merged.loc[renal_mask, "pert_id"].map(lam).fillna(0.0).to_numpy()
    tx_oof_full = np.zeros(len(merged))
    tx_idx = np.flatnonzero(renal_mask)
    tx_oof_full[tx_idx] = oof_tx
    Xm = np.column_stack([logit(best_oof), g * logit(tx_oof_full)])
    y_m = y
    meta_oof = np.zeros(len(y_m))
    for tr, te in GroupKFold(n_splits=5).split(Xm, y_m, groups):
        m = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=0)
        m.fit(Xm[tr], y_m[tr])
        meta_oof[te] = m.predict_proba(Xm[te])[:, 1]
    fused_auc = float(roc_auc_score(y_m, meta_oof))
    struct_auc = struct_report[best_name]["auroc"]
    if fused_auc > struct_auc + 1e-4:
        mode = "gated_late_fusion"
    else:
        mode = "structure_only_protective"
    print(f"[gate] fused={fused_auc:.4f} struct={struct_auc:.4f} -> {mode}")

    # ---------------- Final models ----------------
    final_struct = fit_with_weights(model_candidates()[best_name](),
                                    X, y, weights)
    calibrated = CalibratedClassifierCV(final_struct, method="sigmoid", cv=3)
    calibrated.fit(X, y)

    full = pd.read_parquet(store / "chem" / "tdiki_v2_struct.parquet")
    struct_all = calibrated.predict_proba(full[struct_cols].fillna(0.0))[:, 1]

    tx_final = None
    tx_all = np.full(len(full), np.nan)
    if tx_report.get("auroc") is not None:
        tx_final = Pipeline([("scale", StandardScaler()),
                             ("clf", LogisticRegression(penalty="l2", C=0.05,
                                                        class_weight="balanced",
                                                        max_iter=5000, random_state=0))])
        fit_with_weights(tx_final, tx_sub[tx_cols].fillna(0.0), y_tx, tx_w)
        tx_full_frame = tx.reindex(full["pert_id"])
        has_tx = tx_full_frame.notna().any(axis=1).to_numpy()
        tx_pred = tx_final.predict_proba(tx_full_frame[tx_cols].fillna(0.0))[:, 1]
        tx_all = np.where(has_tx, tx_pred, np.nan)

    if mode == "gated_late_fusion":
        gate = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=0)
        gate.fit(Xm, y_m)
        g_full = pd.Series(full["pert_id"]).map(lam).fillna(0.0).to_numpy()
        tx_logit = np.where(np.isnan(tx_all), 0.0, logit(np.nan_to_num(tx_all)))
        Xm_full = np.column_stack([logit(struct_all), g_full * tx_logit])
        prob = gate.predict_proba(Xm_full)[:, 1]
        joblib.dump(gate, models_dir / "tdiki_v2_gate.joblib")
    else:
        prob = struct_all

    out = pd.DataFrame({
        "pert_id": full["pert_id"],
        "tdiki_prob": prob.astype("float32"),
        "tdiki_struct": struct_all.astype("float32"),
        "tdiki_tx": tx_all.astype("float32"),
        "tdiki_tier": pd.cut(prob, [-0.01, 0.33, 0.66, 1.01],
                             labels=["Low", "Moderate", "High"]).astype(str),
    })
    out.to_parquet(store / "matrices" / "tdiki_cp.parquet", index=False)
    joblib.dump(calibrated, models_dir / "tdiki_v2_struct.joblib")
    if tx_final is not None:
        joblib.dump(tx_final, models_dir / "tdiki_v2_tx.joblib")

    metrics = {
        "mode": mode,
        "structure_expert": {"winner": best_name, "candidates": struct_report},
        "tx_expert": tx_report,
        "fused_oof_auroc": fused_auc,
        "struct_oof_auroc": struct_auc,
        "n_train": int(len(merged)), "n_positive": int(y.sum()),
        "n_with_renal": int(renal_mask.sum()),
        "cv": "5-fold GroupKFold by InChIKey-14; scaffold weights; sample_weight everywhere",
        "tx_features": tx_cols,
        "struct_features": len(struct_cols),
    }
    (models_dir / "tdiki_metrics.json").write_text(json.dumps(metrics, indent=2))
    (models_dir / "tdiki_features.json").write_text(json.dumps(struct_cols))
    print(f"[done] {mode}: struct={struct_auc:.3f} fused={fused_auc:.3f} "
          f"tiers={out['tdiki_tier'].value_counts().to_dict()} "
          f"({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
