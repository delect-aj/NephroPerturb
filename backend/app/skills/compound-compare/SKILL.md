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
  - Safety & Clinical Maturity Comparison
  - Anti-Fibrotic vs. Metabolic/Podocyte Pathways
  - Literature & Clinical Trial Standing
  - Recommendation
example_prompt: "Compare dexamethasone and losartan head-to-head on renal fibrosis modules, podocyte protection, T-DIKI safety, and kidney literature"
---
## Execution Protocol (Strictly Deterministic & Token-Lean)
1. **Head-to-Head Matrix**: Extract 2-4 compound names or resolve `#1`/`#2`/`#3` from the session ledger and call `compare_compounds` ONCE.
2. **Evidence Enrichment**: Call `search_literature` (and `search_clinical_trials` if within step budget) on the top 2 compared compounds (skip if already cached in session ledger).
3. **Stop & Synthesize**: Contrast safety (`tdiki_tier`, `diril_label`), `ECM_fibrosis` / `TGFb_SMAD` suppression, `Podocyte_slit` / `PT_FAO_mito` preservation, and real-world `[PMID:<id>]` / `[NCT<id>]` evidence. End with a concrete context-dependent pick in <= 220 words.
