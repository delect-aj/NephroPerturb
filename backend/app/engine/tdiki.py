"""T-DIKI v2 explanation: instant SQLite lookup in lite/precomputed mode,
falling back to joblib struct model if tdiki_explain table is absent."""
import json

import numpy as np
import pandas as pd

from ..core.store import get_store

_MODEL = {}


def _load():
    if "cal" not in _MODEL:
        import joblib
        store = get_store()
        _MODEL["cal"] = joblib.load(store.store / "models" / "tdiki_v2_struct.joblib")
        _MODEL["struct"] = pd.read_parquet(
            store.store / "chem" / "tdiki_v2_struct.parquet").set_index("pert_id")
        _MODEL["tdiki"] = pd.read_parquet(
            store.store / "matrices" / "tdiki_cp.parquet").set_index("pert_id")
    return _MODEL


def _base_estimator(cal):
    if hasattr(cal, "calibrated_classifiers_") and cal.calibrated_classifiers_:
        return cal.calibrated_classifiers_[0].estimator
    return cal


def explain(pert_id, top_n=10):
    store = get_store()
    con = store.db()
    try:
        cur = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tdiki_explain'"
        )
        if cur.fetchone() is not None:
            row = con.execute(
                "SELECT tdiki_struct, tdiki_prob, tdiki_tier, tdiki_tx, contributions_json "
                "FROM tdiki_explain WHERE pert_id = ?",
                (pert_id,),
            ).fetchone()
            if row is not None:
                contribs = json.loads(row[4] or "[]")[:top_n]
                return {
                    "pert_id": pert_id,
                    "tdiki_struct": row[0],
                    "tdiki_prob": row[1],
                    "tdiki_tier": row[2],
                    "tdiki_tx": row[3],
                    "contributions": contribs,
                }
    finally:
        con.close()

    if store.is_lite:
        raise KeyError(f"{pert_id} has no precomputed structural explanation")

    M = _load()
    if pert_id not in M["struct"].index:
        raise KeyError(f"{pert_id} has no structural features")
    row = M["struct"].loc[pert_id]
    if isinstance(row, pd.DataFrame):
        row = row.iloc[0]
    feat_cols = list(M["struct"].columns)
    x = row[feat_cols].astype(float).fillna(0.0).to_numpy().reshape(1, -1)
    prob_struct = float(M["cal"].predict_proba(x)[0, 1])

    contributions = []
    est = _base_estimator(M["cal"])
    names = np.array(feat_cols)
    try:
        if hasattr(est, "named_steps") and "clf" in est.named_steps:
            clf = est.named_steps["clf"]
            xs = x
            if "scale" in est.named_steps:
                xs = est.named_steps["scale"].transform(x)
            if hasattr(clf, "coef_"):
                if "select" in est.named_steps and hasattr(
                        est.named_steps["select"], "get_support"):
                    sel = est.named_steps["select"].get_support()
                    xsel = est.named_steps["select"].transform(xs)[0]
                    values = clf.coef_[0] * xsel
                    names = names[sel]
                else:
                    values = clf.coef_[0] * xs[0]
                order = np.argsort(-np.abs(values))[:top_n]
                contributions = [{"feature": str(names[i]),
                                  "contribution": float(values[i]),
                                  "value": float(xs[0][i])} for i in order]
        elif hasattr(est, "feature_importances_"):
            values = est.feature_importances_
            order = np.argsort(-values)[:top_n]
            contributions = [{"feature": str(names[i]),
                              "contribution": float(values[i]),
                              "value": float(x[0][i])} for i in order]
    except Exception:  # noqa: BLE001
        contributions = []

    out = {"pert_id": pert_id, "tdiki_struct": prob_struct,
           "contributions": contributions}
    if pert_id in M["tdiki"].index:
        trow = M["tdiki"].loc[pert_id]
        if isinstance(trow, pd.DataFrame):
            trow = trow.iloc[0]
        out["tdiki_prob"] = float(trow["tdiki_prob"])
        out["tdiki_tier"] = str(trow.get("tdiki_tier", "NA"))
        tx = trow.get("tdiki_tx")
        out["tdiki_tx"] = None if pd.isna(tx) else float(tx)
    return json.loads(json.dumps(out, default=str))
