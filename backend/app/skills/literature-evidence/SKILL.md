---
id: literature-evidence
name: Bidirectional Literature & Clinical Audit
short_label: Literature & Trials
description: Search Europe PMC, PubMed, and ClinicalTrials.gov for both renal therapeutic efficacy and drug-induced kidney injury evidence.
color: "#0284c7"
max_steps: 5
allowed_tools:
  - search_literature
  - search_clinical_trials
  - profile_compound
requires_literature: true
output_sections:
  - "1. Executive Evidence Verdict & Novelty"
  - "2. Synthesized Kidney Efficacy Literature"
  - "3. Integrated Nephrotoxicity & Clinical Trials Review"
  - "4. Translational Takeaway"
example_prompt: "Check Europe PMC literature, nephrotoxicity reports, and clinical trials for dexamethasone in diabetic kidney disease"
---
## Execution Protocol
1. Resolve up to 2 target compounds or genes (including session references `#1`, `#2`).
2. Batch `search_literature(entity=..., disease_context=..., include_safety=true)` + `search_clinical_trials` (plus `profile_compound` if NephroSafe toxicity metrics are not yet available).

## Fixed Output Format (Natural Biomedical Prose — Never Print Raw JSON Variable Names like `evidence_tier` or `tdiki_tier`)
### 1. Executive Evidence Verdict & Novelty
Write 2-3 cohesive sentences summarizing overall evidence maturity, the balance of therapeutic versus renal toxicity publications, and whether the candidate is an established renal therapy or a novel repurposing lead with no prior kidney literature.
### 2. Synthesized Kidney Efficacy Literature
Write **one to two cohesive paragraphs** synthesizing experimental models, clinical outcomes, and biological mechanisms across the retrieved studies with inline `[PMID:<digits>]` citations (never list raw article titles one by one).
### 3. Integrated Nephrotoxicity & Clinical Trials Review
Write one cohesive paragraph integrating published renal safety warnings (`[PMID:<digits>]`) with predicted T-DIKI and FDA DIRIL assessments, followed by a summary of registered ClinicalTrials.gov studies (`[NCT<8-digits>]`, trial phase, and recruitment status).
### 4. Translational Takeaway
Write 2 concise sentences weighing therapeutic evidence against renal safety considerations. Do NOT write a manual References section (auto-appended). Never invent identifiers or numbers.
