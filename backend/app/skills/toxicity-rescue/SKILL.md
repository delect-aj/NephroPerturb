---
id: toxicity-rescue
name: Compound Safety & Toxicity Rescue
short_label: Safety & Rescue
description: Audit a drug's kidney toxicity (T-DIKI v2 + DIRIL), explain attribution drivers, and rescue with safer Low-DIKI structural analogs.
color: "#dc2626"
max_steps: 5
allowed_tools:
  - profile_compound
  - explain_tdiki
  - find_safe_analogs
  - search_literature
  - search_clinical_trials
requires_literature: true
output_sections:
  - "1. NephroSafe Verdict & Attribution Rationale"
  - "2. Safer Structural Analog Rescue"
  - "3. Integrated Literature & Clinical Review"
  - "4. Translational Recommendation & Next Steps"
example_prompt: "Is tacrolimus nephrotoxic? Explain its T-DIKI drivers, check nephrotoxicity literature, and find safer Low T-DIKI analogs"
---
## Execution Protocol
1. Batch `profile_compound` + `explain_tdiki` for the target compound (prefer exact `pert_id` once resolved).
2. If `tdiki_tier` is `High`/`Moderate`, `diril_label == 1`, or user requests safer alternatives, call `find_safe_analogs(compound=..., max_diki_tier="Low", top_k=10)`.
3. Batch `search_literature(entity=<name>, include_safety=true)` + `search_clinical_trials` on the query compound.

## Fixed Output Format (Cohesive Academic Prose — No Mechanical Bullet Listing)
### 1. NephroSafe Verdict & Attribution Rationale
Write one concise paragraph stating `tdiki_tier`, `tdiki_prob`, `DIRIL` status, `tdiki_struct`/`tdiki_tx`, and how the top attribution drivers and K-PRL gene shifts explain its renal risk.
### 2. Safer Structural Analog Rescue
State clearly how many `Low` T-DIKI distinct analogs exist in the top 120 ECFP4 neighbors (explicitly note if 0), followed by a compact 3-row Markdown table (`Rank | Analog | pert_id | Tanimoto | T-DIKI | MoA`).
### 3. Integrated Literature & Clinical Review
Write **two cohesive prose paragraphs** synthesizing the retrieved paper `takeaway`s: Paragraph 1 contrasts renal benefit vs. documented nephrotoxicity mechanisms with inline `[PMID:<digits>]`; Paragraph 2 summarizes registered kidney trials (`[NCT<8-digits>]`, phase/status) and safety monitoring context.
### 4. Translational Recommendation & Next Steps
Write 2 crisp sentences advising on risk mitigation and whether a structural analog or scaffold switch is warranted. Do NOT write a manual References section (auto-appended). Never invent IDs or numbers.
