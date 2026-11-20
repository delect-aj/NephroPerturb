#!/usr/bin/env bash
# Full offline build pipeline (Tier-0 -> Tier-1 -> models -> DB).
set -euo pipefail
ROOT=${ROOT:-/public/home/dongb/agent/renalkb}
PY=${PY:-/public/home/dongb/miniforge3/envs/nephroperturb/bin/python}
cd "$ROOT"
run() { echo "=== $*"; "$@"; }
run "$PY" scripts/01_build_gene_universe.py
run "$PY" scripts/02_reconstruct_kprl.py
run "$PY" scripts/03_build_chem_core.py
run "$PY" scripts/etl/enrich_hgnc.py
run "$PY" scripts/etl/enrich_repurposing_hub.py
run "$PY" scripts/etl/enrich_diril_diri.py        # FDA DIRIL labels (training gold standard)
run "$PY" scripts/etl/enrich_kidney_expr.py
run "$PY" scripts/04_compute_func_matrices.py
run "$PY" scripts/06_precompute_tau_bg.py
run "$PY" scripts/05_train_tdiki_model.py
run "$PY" scripts/etl/bm2_cohort_deg.py           # Stage-2 cohort signatures + QC
run "$PY" scripts/etl/build_renal_cases.py        # real cohorts -> config/renal_cases.yaml
run "$PY" scripts/etl/enrich_diril_ctd.py         # SIDER/CTD/FAERS display-only evidence
run "$PY" scripts/07_build_sqlite_pg_db.py
run "$PY" scripts/validate_phase1.py
echo "=== BM-1 (MoA) / BM-2 (real cohorts) / BM-3 (T-DIKI v2) / BM-4 (agent)"
run "$PY" benchmarks/bm1_moa_target_ablation.py
run "$PY" benchmarks/bm2_kidney_cohorts.py
run "$PY" benchmarks/bm3_diril_tdiki_cv.py
run "$PY" benchmarks/bm4_latency_agent_eval.py
