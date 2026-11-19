"""Per-compound T-DIKI explanation (linear model contributions)."""
import json

import joblib
import numpy as np

from ..core.store import get_store

_MODEL = {}
_PREFIX = {"progeny": "pw_", "collectri": "tf_", "renal_modules": "mod_"}


def _load():
    if "model" not in _MODEL:
        store = get_store()
        path = store.store / "models" / "tdiki_model_elasticnet.joblib"
        _MODEL["model"] = joblib.load(path)
        _MODEL["features"] = json.loads(
            (store.store / "models" / "tdiki_features.json").read_text())
        _MODEL["selected"] = json.loads(
            (store.store / "models" / "tdiki_selected_features.json").read_text())
    return _MODEL["model"], _MODEL["features"], _MODEL["selected"]


def feature_row(pert_id):
    store = get_store()
    row_idx = int(store.cp_index.set_index("pert_id").loc[pert_id, "matrix_row_idx"])
    values = {}
    kprl = store.matrix("kprl")
    genes = store.genes
    marker = ["HSPA1A", "HSPH1", "DDIT3", "ATF4", "ATF6", "HSPA5", "XBP1", "ERN1",
              "CDKN1A", "GADD45A", "MDM2", "BBC3", "BAX", "TP53", "HMOX1", "NQO1",
              "TXNRD1", "GCLM", "SLC7A11", "GPX4", "SQSTM1", "MAP1LC3B", "BECN1",
              "ATG5", "HAVCR1", "LCN2", "SPP1", "SOX9", "VCAM1", "IL6", "CXCL8",
              "CCL2", "NFKB1", "RELA", "COL1A1", "COL3A1", "FN1", "SERPINE1",
              "TGFB1", "HIF1A", "VEGFA", "CA9", "LDHA", "SLC2A1", "PPARA",
              "PPARGC1A", "CPT1A", "ACADM", "CASP1", "NLRP3", "GSDMD", "IL1B", "IL18"]
    sym2col = {s.upper(): i for i, s in enumerate(genes["symbol"])}
    for g in marker:
        if g in sym2col:
            values[f"gex_{g}"] = float(kprl[row_idx, sym2col[g]])
    for name, prefix in _PREFIX.items():
        frame = store.func_matrix(name)
        pid = store.cp_index["pert_id"].iloc[row_idx]
        if pid in frame.index:
            for col, val in frame.loc[pid].items():
                values[col] = float(val)
        else:
            for col in frame.columns:
                values[col] = 0.0
    compound = store.compounds.loc[pert_id]
    if hasattr(compound, "ndim") and compound.ndim > 1:
        compound = compound.iloc[0]
    for col in ("mw", "logp", "tpsa", "hbd", "hba", "rotb", "qed", "lipinski_violations"):
        values[col] = float(compound.get(col) or 0.0)
    ecfp = np.load(store.store / "chem" / "ecfp4_cp.npy", mmap_mode="r")
    if "fp_index" not in _MODEL:
        _MODEL["fp_index"] = {pid: i for i, pid in enumerate(store.compounds["pert_id"])}
    ecfp_row = ecfp[_MODEL["fp_index"][pert_id]]
    for i, bit in enumerate(ecfp_row):
        values[f"fp_{i}"] = float(bit)
    return values


def explain(pert_id, top_n=10):
    model, features, selected = _load()
    values = feature_row(pert_id)
    x_full = np.array([values.get(f, 0.0) for f in features], dtype=float)
    scaler = model.named_steps["scale"]
    selector = model.named_steps["select"]
    coef = model.named_steps["clf"].coef_[0]
    x_scaled = scaler.transform(x_full.reshape(1, -1))
    x_sel = selector.transform(x_scaled)[0]
    contrib = coef * x_sel
    order = np.argsort(-np.abs(contrib))[:top_n]
    return {
        "pert_id": pert_id,
        "tdiki_prob": float(model.predict_proba(x_full.reshape(1, -1))[0, 1]),
        "contributions": [
            {"feature": selected[i], "contribution": float(contrib[i]),
             "value": float(x_sel[i])} for i in order
        ],
    }
