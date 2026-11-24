---
id: toxicity-rescue
name: Compound Safety & Toxicity Rescue
short_label: Safety & Analog Rescue
description: Evaluate a compound's nephrotoxicity risk (T-DIKI v2 and FDA DIRIL), explain risk drivers, and identify safer structural analogs.
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
1. Batch `profile_compound` + `explain_tdiki` for the target compound (use exact `pert_id` once resolved).
2. If predicted risk is `High` or `Moderate`, `diril_label == 1`, or the user requests safer alternatives, call `find_safe_analogs(compound=..., max_diki_tier="Low", top_k=10)`.
3. Batch `search_literature(entity=<name>, include_safety=true)` + `search_clinical_trials` on the queried compound.

## Fixed Output Format (Natural Biomedical Prose — Never Print Raw JSON Variable Names like `tdiki_tier` or `diril_label`)
### 1. NephroSafe Verdict & Attribution Rationale
Write one cohesive paragraph stating the compound's predicted T-DIKI risk tier and probability, FDA DIRIL classification, structural and transcriptional risk components, and how the primary chemical descriptors and kidney gene perturbations explain its renal liability.
### 2. Safer Structural Analog Rescue
State clearly how many distinct low-risk analogs were identified among the top 120 ECFP4 structural neighbors (explicitly note if none were found), followed by a compact 3-row Markdown table (`Rank | Analog | pert_id | Tanimoto | T-DIKI | MoA`).
### 3. Integrated Literature & Clinical Review
Write **two cohesive prose paragraphs**: Paragraph 1 contrasts therapeutic renal effects against published nephrotoxicity mechanisms with inline `[PMID:<digits>]` citations; Paragraph 2 summarizes registered kidney clinical trials (`[NCT<8-digits>]`, phase, and status) and clinical monitoring considerations.
### 4. Translational Recommendation & Next Steps
Write 2 concise sentences advising on renal risk mitigation and whether substituting a structural analog or switching chemical scaffolds is warranted. Do NOT write a manual References section (auto-appended). Never invent identifiers or numbers.
