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
  - "1. Computational Screening & NephroSafe Audit"
  - "2. Mechanism of Top Safe Candidate"
  - "3. Literature & Clinical Synthesis"
  - "4. Actionable Recommendation"
example_prompt: "Find reversal drugs for the DKD glomeruli case, auto-filter High T-DIKI hits if needed, and verify literature & clinical trials for top candidates"
---
## Execution Protocol
1. Run one screen (`run_cohort_case`, `score_gene_signature`, or `query_pathway_tf`).
2. Inspect Top-3 hits: if any has `tdiki_tier == "High"` or `diril_label == 1`, AUTOMATICALLY run a safe re-screen (`approved_only=true, max_diki_tier="Low"`) or `find_safe_analogs`.
3. Call `profile_compound` using the **exact `pert_id` (`BRD-...`)** of the #1 safe candidate (not just name).
4. Batch `search_literature` + `search_clinical_trials` for the Top 1-2 safe candidates (by compound name) passing the disease context.

## Fixed Output Format (Use Exact Headings)
### 1. Computational Screening & NephroSafe Audit
State cohort/signature context, whether auto-filtering ran, and Top-3 ranked drugs with exact `pert_id`, score, `T-DIKI`, and `DIRIL`.
### 2. Mechanism of Top Safe Candidate
Summarize MoA, targets, top PROGENy / renal modules, and top K-PRL genes for the #1 profiled candidate.
### 3. Literature & Clinical Synthesis
For each audited drug write concise bullets synthesized from paper `takeaway`s (do NOT list bare counts only):
- **Evidence Verdict & Novelty**: overall `evidence_tier` and novelty standing (`Novel (0 renal papers)` if zero efficacy hits).
- **Efficacy Findings**: concrete disease/model conclusions from `takeaway`s with inline `[PMID:<digits>]`.
- **Nephrotoxicity Signals**: safety findings with `[PMID:<digits>]` (or state none indexed).
- **Clinical Trials**: registered study phases/status/scope with `[NCT<8-digits>]` (or state 0 trials).
### 4. Actionable Recommendation
One grounded sentence naming the top priority candidate and rationale. Never invent PMIDs, NCTs, BRDs, or numbers.
