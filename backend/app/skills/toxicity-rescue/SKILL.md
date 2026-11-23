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
  - "1. NephroSafe Verdict & T-DIKI Drivers"
  - "2. Safer Structural Analog Rescue"
  - "3. Literature & Clinical Synthesis"
  - "4. Actionable Recommendation"
example_prompt: "Is tacrolimus nephrotoxic? Explain its T-DIKI drivers, check nephrotoxicity literature, and find safer Low T-DIKI analogs"
---
## Execution Protocol
1. Batch `profile_compound` + `explain_tdiki` for the target compound (prefer exact `pert_id` once resolved).
2. If `tdiki_tier` is `High`/`Moderate`, `diril_label == 1`, or user requests alternatives, call `find_safe_analogs(compound=..., max_diki_tier="Low", top_k=10)`.
3. Batch `search_literature(entity=<name>, include_safety=true)` + `search_clinical_trials` on the query compound.

## Fixed Output Format (Use Exact Headings)
### 1. NephroSafe Verdict & T-DIKI Drivers
State `tdiki_tier`, `tdiki_prob`, `DIRIL` label, `tdiki_struct`/`tdiki_tx`, and top SHAP/attribution feature contributors.
### 2. Safer Structural Analog Rescue
Report `safe_analogs_found` (or explicitly state if 0 `Low` T-DIKI analogs existed in top 120) and list Top-3 distinct neighbors with `pert_id`, Tanimoto, T-DIKI, and MoA.
### 3. Literature & Clinical Synthesis
Synthesize retrieved paper `takeaway`s into 4 concise bullets:
- **Evidence Verdict**: tier plus efficacy vs. safety hit counts.
- **Kidney Efficacy Findings**: key outcomes/mechanisms with `[PMID:<digits>]`.
- **Nephrotoxicity Safety Audit**: documented renal toxicity mechanisms/warnings with `[PMID:<digits>]`.
- **Clinical Trials**: relevant trial status/phases with `[NCT<8-digits>]` (or state 0 trials).
### 4. Actionable Recommendation
Concise safety guidance and whether a rescued analog is viable. Never invent PMIDs, NCTs, BRDs, or numbers.
