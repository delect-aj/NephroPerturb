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
  - Evidence Tier Verdict
  - Kidney Efficacy Literature
  - Nephrotoxicity Safety Reports
  - Registered Clinical Trials
example_prompt: "Check Europe PMC literature, nephrotoxicity reports, and clinical trials for dexamethasone in diabetic kidney disease"
---
## Execution Protocol (Strictly Deterministic & Token-Lean)
1. **Resolve Entities**: Identify up to 2 target drugs/genes from the query or session ledger (`#1`, `#2`, etc.). Optionally call `profile_compound` if NephroSafe `tdiki_tier` is missing for a compound.
2. **Bidirectional Literature**: Call `search_literature(entity=..., disease_context=..., include_safety=true)` for each target (max 2 targets).
3. **Clinical Trials**: Call `search_clinical_trials(compound=..., condition=...)` for each compound.
4. **Stop & Synthesize**: Summarize overall `evidence_tier`, separate efficacy findings from nephrotoxicity warnings, highlight `Novel (0 renal papers)` when empty, and cite ONLY observed `[PMID:<id>]` and `[NCT<id>]` identifiers (<= 220 words).
