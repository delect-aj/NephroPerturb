#!/usr/bin/env python
"""Train and apply the T-DIKI dual-modality nephrotoxicity model.

Labels: FDA DIRIL 2024 (171 positive / 146 negative drugs).
Features: K-PRL transcriptomic toxicology space (PROGENy, CollecTRI, curated
renal modules, marker genes) + ECFP4 + RDKit descriptors.
Validation: 5-fold GroupKFold on InChIKey-14 (no scaffold leakage).
"""
import json
import sys
import time
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, balanced_accuracy_score, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import paths

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
DESCRIPTORS = ["mw", "logp", "tpsa", "hbd", "hba", "rotb", "qed", "lipinski_violations"]


def load_features(store):
    cp = pd.read_parquet(store / "cp_index.parquet")[["pert_id", "matrix_row_idx"]]
    genes = pd.read_parquet(store / "genes" / "gene_universe.parquet")
    sym2col = {s.upper(): i for i, s in enumerate(genes["symbol"])}

    kprl = np.load(store / "matrices" / "kprl_cp_zscore.npy", mmap_mode="r")
    marker_cols = [sym2col[g] for g in MARKER_GENES if g in sym2col]
    marker_names = [g for g in MARKER_GENES if g in sym2col]
    marker = pd.DataFrame(np.asarray(kprl[:, marker_cols]),
                          columns=[f"gex_{g}" for g in marker_names])
    marker.insert(0, "pert_id", cp["pert_id"].values)

    blocks = [marker.set_index("pert_id")]
    for name, prefix in (("progeny", "pw_"), ("collectri", "tf_"),
                         ("renal_modules", "mod_")):
        frame = pd.read_parquet(store / "matrices" / f"{name}_cp.parquet").set_index("pert_id")
        frame.columns = [prefix + str(c) for c in frame.columns]
        blocks.append(frame)
    X = pd.concat(blocks, axis=1)

    compounds = pd.read_parquet(store / "chem" / "compounds.parquet")
    ecfp = np.load(store / "chem" / "ecfp4_cp.npy")
    compound_features = compounds[["pert_id", "inchikey14"] + DESCRIPTORS].copy()
    fp = pd.DataFrame(ecfp, columns=[f"fp_{i}" for i in range(ecfp.shape[1])])
    fp.insert(0, "pert_id", compounds["pert_id"].values)
    compound_features = pd.concat([compound_features.reset_index(drop=True),
                                   fp.reset_index(drop=True)], axis=1)
    compound_features = compound_features.loc[:, ~compound_features.columns.duplicated()]
    full = compound_features.merge(X.reset_index(), on="pert_id", how="left")
    full = full.fillna(0.0)
    return full


def make_lgb():
    return lgb.LGBMClassifier(
        n_estimators=400, learning_rate=0.03, num_leaves=15, max_depth=5,
        min_child_samples=10, subsample=0.8, subsample_freq=1,
        colsample_bytree=0.15, reg_lambda=1.0, class_weight="balanced",
        random_state=0, verbosity=-1)


def make_enet():
    return Pipeline([
        ("scale", StandardScaler()),
        ("select", SelectKBest(f_classif, k=120)),
        ("clf", LogisticRegression(penalty="elasticnet", solver="saga", l1_ratio=0.5,
                                   C=0.05, class_weight="balanced", max_iter=5000,
                                   random_state=0)),
    ])


def cross_validate(train, feat_cols, groups, weights):
    cv = GroupKFold(n_splits=5)
    results = {}
    for name, builder in (("lightgbm", make_lgb), ("elasticnet", make_enet)):
        oof = np.zeros(len(train))
        for fold, (tr, te) in enumerate(cv.split(train, groups=groups)):
            model = builder()
            model.fit(train.iloc[tr][feat_cols], train.iloc[tr]["diril_label"],
                      **({"sample_weight": weights[tr]} if name == "lightgbm" else {}))
            oof[te] = model.predict_proba(train.iloc[te][feat_cols])[:, 1]
        auc = float(roc_auc_score(train["diril_label"], oof))
        ap = float(average_precision_score(train["diril_label"], oof))
        results[name] = {"oof": oof, "auroc": auc, "auprc": ap}
        print(f"[cv] {name}: auroc={auc:.3f} auprc={ap:.3f}")
    return results


def main():
    t0 = time.time()
    store = paths()["store"]
    models_dir = store / "models"
    models_dir.mkdir(parents=True, exist_ok=True)

    full = load_features(store)
    labels = pd.read_parquet(store / "annotations" / "nephrotoxicity_diril.parquet")
    train = full.merge(labels[["pert_id", "diril_label"]], on="pert_id", how="inner")
    feat_cols = [c for c in full.columns if c not in ("pert_id", "inchikey14", "diril_label")]
    print(f"[features] {len(feat_cols)} features | labeled compounds {len(train)} "
          f"(pos={int(train['diril_label'].sum())})")

    groups = train["inchikey14"].astype("string").fillna("")
    groups = groups.where(groups.str.len() > 4, train["pert_id"].astype("string")).astype(str)
    weights = 1.0 / groups.map(groups.value_counts()).to_numpy()
    weights = weights / weights.mean()

    results = cross_validate(train, feat_cols, groups, weights)
    best_name = max(results, key=lambda k: results[k]["auroc"])
    oof = results[best_name]["oof"]
    metrics = {
        "best_model": best_name,
        "auroc": results[best_name]["auroc"],
        "auprc": results[best_name]["auprc"],
        "auroc_lightgbm": results["lightgbm"]["auroc"],
        "auroc_elasticnet": results["elasticnet"]["auroc"],
        "balanced_accuracy": float(balanced_accuracy_score(
            train["diril_label"], (oof >= 0.5).astype(int))),
        "n_train": int(len(train)),
        "n_positive": int(train["diril_label"].sum()),
        "n_features": int(len(feat_cols)),
        "cv": "5-fold GroupKFold by InChIKey-14",
    }
    print("[cv]", json.dumps({k: round(v, 4) if isinstance(v, float) else v
                              for k, v in metrics.items()}))

    model = make_lgb() if best_name == "lightgbm" else make_enet()
    fit_kwargs = {"sample_weight": weights} if best_name == "lightgbm" else {}
    model.fit(train[feat_cols], train["diril_label"], **fit_kwargs)
    if best_name == "lightgbm":
        model.booster_.save_model(str(models_dir / "tdiki_model.txt"))
    joblib.dump(model, models_dir / f"tdiki_model_{best_name}.joblib")

    prob = model.predict_proba(full[feat_cols])[:, 1]
    out = pd.DataFrame({
        "pert_id": full["pert_id"],
        "tdiki_prob": prob.astype("float32"),
        "tdiki_tier": pd.cut(prob, [-0.01, 0.33, 0.66, 1.01],
                             labels=["Low", "Moderate", "High"]).astype(str),
    })
    out.to_parquet(store / "matrices" / "tdiki_cp.parquet", index=False)

    if best_name == "lightgbm":
        importance = pd.DataFrame({
            "feature": feat_cols,
            "importance": model.booster_.feature_importance(importance_type="gain"),
        })
    else:
        selected = np.asarray(model.named_steps["select"].get_support())
        coefs = model.named_steps["clf"].coef_[0]
        importance = pd.DataFrame({
            "feature": np.array(feat_cols)[selected],
            "importance": np.abs(coefs),
        })
        (models_dir / "tdiki_selected_features.json").write_text(
            json.dumps(list(np.array(feat_cols)[selected])))
    importance.sort_values("importance", ascending=False).to_parquet(
        models_dir / "tdiki_feature_importance.parquet", index=False)
    (models_dir / "tdiki_metrics.json").write_text(json.dumps(metrics, indent=2))
    (models_dir / "tdiki_features.json").write_text(json.dumps(feat_cols))

    print(f"[done] scored {len(out)} compounds | "
          f"tiers {out['tdiki_tier'].value_counts().to_dict()} | {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
