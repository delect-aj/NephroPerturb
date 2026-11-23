---
id: disease-repurposing
name: Disease-to-Evidence Repurposing
short_label: Disease -> Evidence
description: Screen cohorts, gene signatures, or pathways with automatic high-toxicity re-screening and integrated literature review.
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
  - "1. Executive Synthesis & Prioritized Candidates"
  - "2. Mechanistic & NephroSafe Rationale"
  - "3. Integrated Literature & Clinical Review"
  - "4. Translational Recommendation & Next Steps"
example_prompt: "Find reversal drugs for the DKD glomeruli case, auto-filter High T-DIKI hits if needed, and verify literature & clinical trials for top candidates"
---
## Execution Protocol
1. Run one screen (`run_cohort_case`, `score_gene_signature`, or `query_pathway_tf`).
2. Inspect Top-3 hits: if any has `tdiki_tier == "High"` or `diril_label == 1`, AUTOMATICALLY run a safe re-screen (`approved_only=true, max_diki_tier="Low"`) or `find_safe_analogs`.
3. Call `profile_compound` using the **exact `pert_id` (`BRD-...`)** of the #1 safe candidate.
4. Batch `search_literature` + `search_clinical_trials` for the Top 1-2 safe candidates (by name) in the active disease context.

## Fixed Output Format (Cohesive Academic Prose — No Mechanical Bullet Listing)
### 1. Executive Synthesis & Prioritized Candidates
Write 2-3 cohesive sentences stating the screened cohort/signature, whether auto-filtering ran, and why the top leads stand out, followed by a compact 3-row Markdown table (`Rank | Compound | pert_id | Score | T-DIKI | DIRIL | Phase`).
### 2. Mechanistic & NephroSafe Rationale
Write one flowing paragraph explaining how the #1 profiled candidate's MoA, PROGENy pathways, renal modules, and key K-PRL genes counter disease pathology while preserving renal safety.
### 3. Integrated Literature & Clinical Review
Write **two cohesive prose paragraphs** (do NOT use choppy key-value bullets):
- Paragraph 1 (*Therapeutic Evidence & Novelty*): Synthesize concrete preclinical/clinical findings across the retrieved paper `takeaway`s with inline `[PMID:<digits>]`, distinguishing direct kidney efficacy from indirect mentions or `Novel (0 renal papers)` gaps.
- Paragraph 2 (*Renal Safety & Clinical Pipeline*): Integrate published nephrotoxicity reports (`[PMID:<digits>]`) with NephroSafe T-DIKI/DIRIL risk, and summarize registered kidney trials (`[NCT<8-digits>]`, phase/status).
### 4. Translational Recommendation & Next Steps
Write 2 crisp sentences naming the top lead and concrete experimental or clinical validation steps. Do NOT write a manual References section (auto-appended from your inline `[PMID]`/`[NCT]` citations). Never invent IDs or numbers.
