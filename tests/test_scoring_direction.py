"""Direction invariant for the scoring engine.

A compound that REVERSES the query signature must be rewarded (positive
calibrated tau on every method, positive renalconn) and a compound that
MIMICS the query must be penalized. Catches polarity regressions in
_tau / renalconn fusion.

Run on the server inside the nephroperturb env:
    python tests/test_scoring_direction.py
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def main():
    from app.core.store import get_store
    from app.engine.scoring import rank_all

    store = get_store()
    comp = store.find_compound("dexamethasone")
    assert comp is not None, "dexamethasone not in library"
    pid = comp["pert_id"]
    row = int(comp["matrix_row_idx"])
    z = np.asarray(store.matrix("kprl")[row], dtype=np.float64)
    assert np.isfinite(z).all(), "dexamethasone K-PRL row has non-finite values"
    genes = store.genes
    order = np.argsort(-z)
    up_syms = [str(genes["symbol"].iloc[i]) for i in order[:50]]
    dn_syms = [str(genes["symbol"].iloc[i]) for i in order[::-1][:50]]

    # Mimicry query: the disease state IS dexamethasone's own profile, so
    # dexamethasone must be penalized (negative renalconn).
    mimic = rank_all(up_syms, dn_syms)
    mrow = mimic.loc[mimic["pert_id"] == pid].iloc[0]
    m = float(mrow["renalconn"])
    assert m < 0, f"mimicry must score negative, got renalconn={m}"

    # Reversal query: signature flipped, dexamethasone reverses it and must
    # be rewarded: every tau positive, renalconn positive, top-1% rank.
    rev = rank_all(dn_syms, up_syms)
    rrow = rev.loc[rev["pert_id"] == pid].iloc[0]
    r = float(rrow["renalconn"])
    assert r > 0, f"reversal must score positive, got renalconn={r}"
    for col in ("tau_xsum", "tau_zhang", "tau_wtcs", "tau_func"):
        v = float(rrow[col])
        assert v > 0, f"{col} must be positive on reversal, got {v}"
    better = int((rev["renalconn"] > r).sum())
    assert better <= 0.01 * len(rev), f"expected top-1% rank, got {better} better"
    assert r > m + 100, f"reversal must clearly outrank mimicry: {r:.1f} vs {m:.1f}"
    print(f"test_scoring_direction OK: mimicry={m:.1f} reversal={r:.1f} "
          f"rank={better}/{len(rev)}")


if __name__ == "__main__":
    main()
