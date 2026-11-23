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
  - "1. Evidence Verdict & Novelty"
  - "2. Efficacy Literature Synthesis"
  - "3. Nephrotoxicity & Clinical Trials"
  - "4. Decision Takeaway"
example_prompt: "Check Europe PMC literature, nephrotoxicity reports, and clinical trials for dexamethasone in diabetic kidney disease"
---
## Execution Protocol
1. Resolve up to 2 target drugs/genes (including session references `#1`, `#2`).
2. Batch `search_literature(entity=..., disease_context=..., include_safety=true)` + `search_clinical_trials` (and `profile_compound` if T-DIKI tier is unknown).

## Fixed Output Format (Use Exact Headings)
### 1. Evidence Verdict & Novelty
State per-entity `evidence_tier`, hit counts (`efficacy_total_hits`, `safety_total_hits`), provider, and whether it represents `Novel (0 renal papers)`.
### 2. Efficacy Literature Synthesis
Synthesize concrete biological/clinical conclusions across papers using their `takeaway`s (not just titles), citing `[PMID:<digits>]` after each claim.
### 3. Nephrotoxicity & Clinical Trials
Summarize nephrotoxicity warnings from safety papers (`[PMID:<digits>]`) alongside NephroSafe `T-DIKI`/`DIRIL` status, plus registered kidney trials (`[NCT<8-digits>]` with phase & status).
### 4. Decision Takeaway
One concise translational recommendation grounded in both efficacy and safety evidence. Never invent PMIDs, NCTs, BRDs, or numbers.
