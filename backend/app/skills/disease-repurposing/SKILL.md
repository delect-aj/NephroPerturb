---
id: disease-repurposing
name: Disease-to-Evidence Repurposing
short_label: Disease -> Evidence
description: Screen cohorts, gene signatures, or pathways with automatic high-toxicity re-screening and literature/trial validation.
color: "#2563eb"
max_steps: 6
allowed_tools:
  - run_cohort_case
  - score_gene_signature
  - query_pathway_tf
  - profile_compound
  - find_safe_analogs
  - search_literature
  - search_clinical_trials
requires_literature: true
output_sections:
  - Computational Screening & Safety Audit
  - Top Safe Candidates & Mechanism
  - Literature & Clinical Evidence
  - Next Decisions
example_prompt: "Find reversal drugs for the DKD glomeruli case, filter unsafe high T-DIKI hits if needed, and verify literature & clinical trials for top candidates"
---
## Execution Protocol (Strictly Deterministic & Token-Lean)
1. **Compute Screen**: Run the single matching computational tool first (`run_cohort_case`, `score_gene_signature`, or `query_pathway_tf`).
2. **Reflect on NephroSafe Risk**: Inspect the Top 3 ranked candidates. If any Top-3 candidate has `tdiki_tier == "High"` or `diril_label == 1`, AUTOMATICALLY run a safe follow-up screen with `approved_only=true, max_diki_tier="Low"` (for cohorts/signatures) OR call `find_safe_analogs` on the highest-scoring hit (for pathways). State explicitly what was filtered out and why.
3. **Mechanistic Profile**: Call `profile_compound` on the #1 safe candidate (unless already profiled) to obtain its MoA, targets, and K-PRL direction.
4. **Real-World Evidence (max 2 candidates)**: Call `search_literature` (passing the kidney disease context) and `search_clinical_trials` on the Top 1-2 safe candidates only. Skip #3+ to control latency and tokens.
5. **Stop & Synthesize**: Summarize in concise English (<= 220 words) using ONLY observed numbers, `[PMID:<id>]`, and `[NCT<id>]` tags. Label candidates with 0 efficacy hits explicitly as `Novel (0 renal papers)`. Do NOT invent any PMID, NCT, score, or compound.
