"""Unit tests for the BM-2 metric helpers (stdlib only, no store needed)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))
from bm2_kidney_cohorts import fold_enrichment, median_percentile  # noqa: E402


def test_fold_enrichment():
    # 1000-item library, top window k=10; 9 positives, 8 inside the window.
    ordered = [f"p{i}" for i in range(1000)]
    positives = {f"p{i}" for i in range(8)} | {"p500"}  # 8 in top-10, 1 outside
    fold, hits, k = fold_enrichment(ordered, positives, n_lib=1000)
    assert (hits, k) == (8, 10), (hits, k)
    expected = 9 * 10 / 1000  # random expectation: 0.09 hits
    assert abs(fold - 8 / expected) < 1e-12, fold  # 88.89x


def test_fold_enrichment_empty():
    fold, hits, _ = fold_enrichment([f"x{i}" for i in range(50)], set(), n_lib=50)
    assert fold == 0.0 and hits == 0


def test_median_percentile():
    ordered = [f"g{i}" for i in range(100)]
    positives = {"g0", "g49", "g99"}
    med, pcts = median_percentile(ordered, positives, n_lib=100)
    assert abs(med - 0.49) < 1e-12, med
    assert abs(pcts["g0"] - 0.0) < 1e-12 and abs(pcts["g99"] - 0.99) < 1e-12


def test_median_percentile_missing_positive():
    med, _ = median_percentile(["a", "b"], {"zzz"}, n_lib=2)
    assert med == 1.0, med


if __name__ == "__main__":
    test_fold_enrichment()
    test_fold_enrichment_empty()
    test_median_percentile()
    test_median_percentile_missing_positive()
    print("test_bm2_metrics OK")
