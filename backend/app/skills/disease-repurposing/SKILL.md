---
id: disease-repurposing
name: Disease-to-Evidence Repurposing
short_label: Disease Repurposing
description: Screen kidney cohorts, gene signatures, or pathways with automatic high-toxicity filtering and integrated literature review.
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
1. Run one primary screen (`run_cohort_case`, `score_gene_signature`, or `query_pathway_tf`).
2. Inspect the top 3 hits: if any candidate has `tdiki_tier == "High"` or `diril_label == 1`, automatically run a filtered re-screen (`approved_only=true, max_diki_tier="Low"`) or `find_safe_analogs`.
3. Call `profile_compound` using the **exact `pert_id` (`BRD-...`)** of the #1 safe candidate.
4. Batch `search_literature` + `search_clinical_trials` for the top 1-2 safe candidates (by compound name) in the active disease context.

## Fixed Output Format (Natural Biomedical Prose — Never Print Raw JSON Variable Names like `tdiki_tier` or `diril_label`)
### 1. Executive Synthesis & Prioritized Candidates
Write 2-3 cohesive sentences stating the screened cohort or signature, whether high-toxicity filtering was triggered, and why the top leads are prioritized, followed by a compact 3-row Markdown table (`Rank | Compound | pert_id | Score | T-DIKI | DIRIL | Phase`).
### 2. Mechanistic & NephroSafe Rationale
Write one flowing paragraph explaining how the top candidate's MoA, targets, PROGENy pathways, and renal modules counter disease pathology while preserving renal safety.
### 3. Integrated Literature & Clinical Review
Write **two cohesive prose paragraphs** (do not use mechanical key-value bullet lists):
- Paragraph 1 (*Therapeutic Evidence & Novelty*): Synthesize preclinical and clinical findings across the retrieved studies with inline `[PMID:<digits>]` citations, distinguishing established renal efficacy from novel repurposing leads with no prior kidney publications.
- Paragraph 2 (*Renal Safety & Clinical Trial Landscape*): Integrate published nephrotoxicity reports (`[PMID:<digits>]`) with predicted T-DIKI and FDA DIRIL assessments, and summarize registered ClinicalTrials.gov studies (`[NCT<8-digits>]`, trial phase, and status).
### 4. Translational Recommendation & Next Steps
Write 2 concise sentences naming the primary lead and proposing a validation assay. Do NOT write a manual References section (auto-appended). Never invent IDs or numbers.
