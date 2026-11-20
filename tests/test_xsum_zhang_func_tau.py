"""Kernel invariants: true XSum symmetry, Zhang bound, func min_n gate,
empirical tau range/monotonicity/direction.

Run on the server: python tests/test_xsum_zhang_func_tau.py
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main():
    from app.core.store import get_store
    from app.engine import scoring as sc

    store = get_store()
    comp = store.find_compound("dexamethasone")
    assert comp is not None
    row = int(comp["matrix_row_idx"])
    z = np.asarray(store.matrix("kprl")[row], dtype=np.float64)
    order = np.argsort(-z)
    up = list(order[:150])
    dn = list(order[::-1][:150])
    up_sym = store.genes.iloc[up]["symbol"].tolist()
    dn_sym = store.genes.iloc[dn]["symbol"].tolist()

    # --- true XSum: reversal symmetry for mirrored queries ---
    s_mimic = sc.xsum_extreme(store, "kprl", up, dn)
    s_rev = sc.xsum_extreme(store, "kprl", dn, up)
    assert s_mimic[row] < 0, f"mimicry xsum must be negative, got {s_mimic[row]}"
    assert s_rev[row] > 0, f"reversal xsum must be positive, got {s_rev[row]}"
    diff = float(np.max(np.abs(s_mimic + s_rev)))
    assert diff < 1e-5, f"mirrored queries must be antisymmetric, max diff {diff}"

    # --- true Zhang: bound in [-1, 1], reversal direction ---
    z_mimic = sc.zhang_score(store, "kprl", up, dn)
    z_rev = sc.zhang_score(store, "kprl", dn, up)
    assert float(np.max(np.abs(z_mimic))) <= 1.0 + 1e-6
    assert z_mimic[row] < 0 and z_rev[row] > 0
    assert abs(float(z_mimic[row] + z_rev[row])) < 1e-6

    # --- WTCS direction (already reversal-positive) ---
    w_mimic = sc.wtcs_score(store, "kprl", up, dn)
    w_rev = sc.wtcs_score(store, "kprl", dn, up)
    assert w_mimic[row] < 0 and w_rev[row] > 0

    # --- func: min_n gate zeroes single-gene queries ---
    f_tiny = sc.func_scores(store, ["TGFB1"], ["COL1A1"], "kprl")
    assert np.allclose(f_tiny, 0.0), "func min_n>=5 gate failed"
    f_real = sc.func_scores(store, up_sym, dn_sym, "kprl")
    assert np.isfinite(f_real).all()

    # --- empirical tau: range, monotonicity, direction ---
    raw_mimic = {
        "xsum": s_mimic, "zhang": z_mimic, "wtcs": w_mimic,
        "func": sc.func_scores(store, up_sym, dn_sym, "kprl"),
    }
    raw_rev = {
        "xsum": s_rev, "zhang": z_rev, "wtcs": w_rev,
        "func": sc.func_scores(store, dn_sym, up_sym, "kprl"),
    }
    for method in sc.METHODS:
        tau_m = sc._quantile_tau(store, method, raw_mimic[method], "kprl")
        tau_r = sc._quantile_tau(store, method, raw_rev[method], "kprl")
        assert tau_m.min() >= -100.0001 and tau_m.max() <= 100.0001
        assert tau_m[row] < 0, f"{method}: mimicry tau must be negative, {tau_m[row]}"
        assert tau_r[row] > 0, f"{method}: reversal tau must be positive, {tau_r[row]}"
    # per-compound monotonicity: tau is a monotone function of the score for
    # ONE compound's own quantile table (cross-compound monotonicity does not
    # hold by construction)
    probe_scores = np.linspace(-1.0, 1.0, 41)
    probe = np.zeros(len(store.cp_index), dtype=np.float32)
    probe[row] = probe_scores[0]
    taus = []
    for s_val in probe_scores:
        arr = probe.copy()
        arr[row] = s_val
        taus.append(float(sc._quantile_tau(store, "xsum", arr, "kprl")[row]))
    assert np.all(np.diff(taus) >= -1e-6), f"per-compound tau not monotone: {taus}"

    print(f"test_xsum_zhang_func_tau OK: xsum={s_mimic[row]:.3f}/{s_rev[row]:.3f} "
          f"zhang={z_mimic[row]:.3f} wtcs={w_mimic[row]:.3f}")


if __name__ == "__main__":
    main()
