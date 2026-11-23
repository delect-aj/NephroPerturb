---
id: literature-evidence
name: Bidirectional Literature & Clinical Audit
short_label: Literature & Trials
description: Run Europe PMC/PubMed efficacy + nephrotoxicity searches and ClinicalTrials.gov v2 lookup with strict PMID/NCT citation verification.
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
1. Resolve up to 2 target drugs/genes (including session references `#1`, `#2`).
2. Batch `search_literature(entity=..., disease_context=..., include_safety=true)` + `search_clinical_trials` (plus `profile_compound` if NephroSafe `T-DIKI` is unknown).

## Fixed Output Format (Cohesive Academic Prose — No Mechanical Bullet Listing)
### 1. Executive Evidence Verdict & Novelty
Write 2-3 cohesive sentences giving the overall `evidence_tier`, efficacy vs. safety publication volume, and whether the candidate represents an established therapy or a `Novel (0 renal papers)` repurposing lead.
### 2. Synthesized Kidney Efficacy Literature
Write **one to two logical prose paragraphs** synthesizing themes, experimental models, clinical outcomes, and mechanisms across the retrieved paper `takeaway`s with inline `[PMID:<digits>]` citations (never simply copy raw titles one-by-one).
### 3. Integrated Nephrotoxicity & Clinical Trials Review
Write one cohesive paragraph integrating published renal toxicity warnings (`[PMID:<digits>]`) with NephroSafe `T-DIKI`/`DIRIL` status, followed by a synthesis of registered ClinicalTrials.gov phases/status (`[NCT<8-digits>]`).
### 4. Translational Takeaway
Write 2 crisp sentences weighing therapeutic promise against safety liability. Do NOT write a manual References section (auto-appended). Never invent IDs or numbers.
