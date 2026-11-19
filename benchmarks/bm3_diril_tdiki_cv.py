#!/usr/bin/env python
"""BM-3: T-DIKI modality ablation and nephrotoxicity false-positive interception."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))
from common import paths  # noqa: E402

OUT = ROOT / "benchmarks" / "outputs"
DESCRIPTORS = ["mw", "logp", "tpsa", "hbd", "hba", "rotb", "qed", "lipinski_violations"]


def model():
    return Pipeline([
        ("scale", StandardScaler()),
        ("select", SelectKBest(f_classif, k=120)),
        ("clf", LogisticRegression(penalty="elasticnet", solver="saga", l1_ratio=0.5,
                                   C=0.05, class_weight="balanced", max_iter=5000,
                                   random_state=0)),
    ])


def cross_val(X, y, groups):
    oof = np.zeros(len(y))
    for tr, te in GroupKFold(n_splits=5).split(X, y, groups):
        clf = model()
        clf.fit(X.iloc[tr], y[tr])
        oof[te] = clf.predict_proba(X.iloc[te])[:, 1]
    return float(roc_auc_score(y, oof)), float(average_precision_score(y, oof))


def main():
    from app.engine.scoring import rank_all
    OUT.mkdir(parents=True, exist_ok=True)
    store = paths()["store"]
    compounds = pd.read_parquet(store / "chem" / "compounds.parquet")
    labels = pd.read_parquet(store / "annotations" / "nephrotoxicity_diril.parquet")
    tdiki = pd.read_parquet(store / "matrices" / "tdiki_cp.parquet")

    markers = ["HSPA1A", "HSPH1", "DDIT3", "ATF4", "ATF6", "HSPA5", "XBP1", "ERN1",
               "CDKN1A", "GADD45A", "MDM2", "BBC3", "BAX", "TP53", "HMOX1", "NQO1",
               "TXNRD1", "GCLM", "SLC7A11", "GPX4", "SQSTM1", "MAP1LC3B", "BECN1",
               "ATG5", "HAVCR1", "LCN2", "SPP1", "SOX9", "VCAM1", "IL6", "CXCL8",
               "CCL2", "NFKB1", "RELA", "COL1A1", "COL3A1", "FN1", "SERPINE1",
               "TGFB1", "HIF1A", "VEGFA", "CA9", "LDHA", "SLC2A1", "PPARA",
               "PPARGC1A", "CPT1A", "ACADM", "CASP1", "NLRP3", "GSDMD", "IL1B", "IL18"]
    genes = pd.read_parquet(store / "genes" / "gene_universe.parquet")
    sym2col = {s.upper(): i for i, s in enumerate(genes["symbol"])}
    kprl = np.load(store / "matrices" / "kprl_cp_zscore.npy", mmap_mode="r")
    cols = [sym2col[m] for m in markers if m in sym2col]
    names = [m for m in markers if m in sym2col]
    transcript = pd.DataFrame(np.asarray(kprl[:, cols]), columns=[f"gex_{n}" for n in names])
    transcript.insert(0, "pert_id", compounds["pert_id"].values)
    for name, prefix in (("progeny", "pw_"), ("collectri", "tf_"), ("renal_modules", "mod_")):
        frame = pd.read_parquet(store / "matrices" / f"{name}_cp.parquet").set_index("pert_id")
        frame.columns = [prefix + str(c) for c in frame.columns]
        transcript = transcript.merge(frame, left_on="pert_id", right_index=True, how="left")

    ecfp = np.load(store / "chem" / "ecfp4_cp.npy")
    structure = compounds[["pert_id"] + DESCRIPTORS].copy()
    fp = pd.DataFrame(ecfp, columns=[f"fp_{i}" for i in range(ecfp.shape[1])])
    structure = pd.concat([structure.reset_index(drop=True), fp], axis=1)
    structure = structure.loc[:, ~structure.columns.duplicated()]

    data = transcript.merge(structure, on="pert_id").merge(
        labels[["pert_id", "diril_label"]], on="pert_id", how="inner")
    data = data.fillna(0.0)
    y = data["diril_label"].to_numpy()
    groups = compounds.set_index("pert_id").loc[data["pert_id"], "inchikey14"]
    groups = groups.astype("string").fillna("")
    groups = groups.where(groups.str.len() > 4, data["pert_id"].astype("string")).astype(str)

    tx_cols = [c for c in transcript.columns if c != "pert_id"]
    st_cols = [c for c in structure.columns if c != "pert_id"]
    report = {"n_train": int(len(data)), "n_positive": int(y.sum())}
    report["transcriptome_only"] = cross_val(data[tx_cols], y, groups)
    report["structure_only"] = cross_val(data[st_cols], y, groups)
    report["dual_modality"] = cross_val(data[tx_cols + st_cols], y, groups)
    print(f"[bm3] {report}")

    cases = yaml.safe_load((ROOT / "config" / "renal_cases.yaml").read_text())["cases"]
    diril_flags = labels.set_index("pert_id")["diril_label"]
    tdiki_prob = tdiki.set_index("pert_id")["tdiki_prob"]
    safety = []
    for case_id, case in cases.items():
        ranking = rank_all(case["up"], case["down"], context="kprl")
        top = ranking.sort_values("renalconn", ascending=False).head(50)
        known = top["pert_id"].map(diril_flags)
        n_bad = int((known == 1).sum())
        filtered = top[top["pert_id"].map(tdiki_prob) < 0.66]
        n_bad_filtered = int((filtered["pert_id"].map(diril_flags) == 1).sum())
        safety.append({"case": case_id, "top50_known_nephrotoxic": n_bad,
                       "top50_after_tdiki_filter": int(len(filtered)),
                       "known_nephrotoxic_after": n_bad_filtered,
                       "reduction": n_bad - n_bad_filtered})
        print(f"[bm3] {case_id}: {safety[-1]}")
    report["safety_filter"] = safety
    (OUT / "bm3_diril_tdiki_cv.json").write_text(json.dumps(report, indent=2))
    print(f"[bm3] wrote {OUT / 'bm3_diril_tdiki_cv.json'}")


if __name__ == "__main__":
    main()
