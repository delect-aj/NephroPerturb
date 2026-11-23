---
id: compound-compare
name: Head-to-Head Compound Comparison
short_label: Compare Drugs
description: Compare 2-4 compounds side-by-side across T-DIKI/DIRIL safety, PROGENy pathways, 9 renal modules, and kidney literature.
color: "#0d9488"
max_steps: 5
allowed_tools:
  - compare_compounds
  - search_literature
  - search_clinical_trials
requires_literature: true
output_sections:
  - "1. Safety & Clinical Maturity Comparison"
  - "2. Pathway & Renal Module Trade-offs"
  - "3. Literature & Clinical Synthesis"
  - "4. Context-Dependent Recommendation"
example_prompt: "Compare dexamethasone and losartan head-to-head on renal fibrosis modules, podocyte protection, T-DIKI safety, and kidney literature"
---
## Execution Protocol
1. Resolve 2-4 compound names or `#1`/`#2` from session ledger and call `compare_compounds`.
2. Batch `search_literature` + `search_clinical_trials` on top 2 compared compounds (reuse ledger if already audited).

## Fixed Output Format (Use Exact Headings)
### 1. Safety & Clinical Maturity Comparison
Compare `clinical_phase`, `MoA`, `tdiki_tier` (`tdiki_prob`), and `DIRIL`, explicitly citing `highlights.safest_kidney`.
### 2. Pathway & Renal Module Trade-offs
Contrast `ECM_fibrosis`, `TGFb_SMAD`, `Podocyte_slit`, `PT_FAO_mito`, and top PROGENy differences with exact numbers.
### 3. Literature & Clinical Synthesis
Compare each compound's `evidence_tier`, key efficacy findings from `takeaway`s (`[PMID:<digits>]`), nephrotoxicity warnings (`[PMID:<digits>]`), and registered kidney trials (`[NCT<8-digits>]`).
### 4. Context-Dependent Recommendation
Name which drug wins for efficacy vs. kidney safety and recommend a clear lead. Never invent PMIDs, NCTs, BRDs, or numbers.
