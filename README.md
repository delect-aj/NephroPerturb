# NephroPerturb

Kidney-context drug perturbation knowledge base: LINCS L1000 Level-5 reconstruction,
kidney-context shrinkage (K-PRL), multi-scale signature reversal, nephrotoxicity
guardrails, and a deterministic Agent / MCP interface.

## Layout

```
config/       settings.yaml, renal_modules.yaml, renal_cases.yaml
scripts/      00 env, 01 genes, 02 K-PRL, 03 chem, 04 function, 05 T-DIKI,
              06 tau null, 07 SQLite, 08 full pipeline, validate_phase1
scripts/etl/  enrich_hgnc, enrich_repurposing_hub, enrich_diril_ctd, enrich_kidney_expr
store/        matrices / chem / annotations / models / downloads / nephroperturb.db
backend/      FastAPI REST + MCP server + SOP router
frontend/     Next.js 14 portal (8 routes)
benchmarks/   BM-1 .. BM-4
deploy/       start/stop/healthcheck/backup/nginx templates
```

## Build

```bash
bash scripts/00_setup_env.sh
bash scripts/08_run_all.sh          # full offline build (~15 min)
```

Artifacts are versioned by content; large matrices are ignored by git and can be
rebuilt from `/public/home/dongb/agent/data/` (read-only upstream).

## Run

```bash
deploy/start_all.sh     # api :8091, mcp :8092, web :3000
deploy/healthcheck.sh
deploy/stop_all.sh
```

## Core outputs

| Object | Shape / content |
|---|---|
| `kprl_cp_zscore.npy` | 21,299 × 12,328 K-PRL continuous z-scores |
| `pan_cp_zscore.npy` | Pan-Cell consensus |
| `renal_epi_cp_zscore.npy` | HA1E/HEK293T/NKDBA consensus |
| `renal_endo_cp_zscore.npy` | HUVEC |
| `renal_immune_cp_zscore.npy` | THP1/U937/JURKAT/HL60 |
| `genetic_consensus.npy` | 31,082 genetic/ligand perturbations |
| `progeny_cp.parquet` | 21,299 × 14 pathways |
| `collectri_cp.parquet` | 21,299 × 725 TFs |
| `renal_modules_cp.parquet` | 21,299 × 13 curated renal modules |
| `tdiki_cp.parquet` | DIRIL-trained dual-modality risk |
| `tau_null_tables.npz` | per-compound random-set nulls for tau calibration |
| `downloads/*.gmt` | split UP_250 / DN_250 for K-PRL, Pan-Cell, Renal-Epi |

## API / MCP

REST: `/api/v1/query/signature`, `/query/pathway-tf`, `/compound/{id}`,
`/compound/{id}/explain`, `/target/{symbol}`, `/similarity/structure`, `/cases`,
`/agent/route`, `/agent/summarize`, `/downloads`.

MCP tools: `nephro_query_signature`, `nephro_profile_compound`,
`nephro_query_pathway_tf`, `nephro_target_mimicry`, `nephro_infer_moa`,
`nephro_list_renal_cases`.

The LLM (DeepSeek, OpenAI-compatible) only maps language to SOP slots and
summarizes returned tables. Every score is deterministic; without
`DEEPSEEK_API_KEY` the platform runs in 0-LLM mode.

## Parameters and caveats

- K-PRL shrinkage: `lambda = n_eff / (n_eff + kappa)`, default `kappa = 0.5`
  selected by the BM-1 kappa sweep.
- The renal epithelial context contains only `HA1E`, `HEK293T`, `NKDBA`
  (these are the renal lines present in the local Level-5 data).
- `renal_cases.yaml` contains compact literature-marker demo signatures, not
  full DEG tables; replace them with cohort signatures for production analyses.
- DIRIL labels come from the FDA DIRIL dataset (317 drugs, 171 positive).
- Kidney expression uses GTEx v8 kidney cortex/medulla, HPA kidney consensus and
  HPA single-cell kidney cell types.

## Benchmarks

Run `python benchmarks/bm*.py`; outputs land in `benchmarks/outputs/`.
BM-1 MoA retrieval, BM-2 kidney cohort recovery, BM-3 T-DIKI modality ablation
and safety interception, BM-4 latency + 0-LLM SOP routing.
