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
  - "1. Head-to-Head Safety & Clinical Maturity"
  - "2. Mechanistic & Renal Module Trade-offs"
  - "3. Integrated Literature & Clinical Review"
  - "4. Context-Dependent Recommendation"
example_prompt: "Compare dexamethasone and losartan head-to-head on renal fibrosis modules, podocyte protection, T-DIKI safety, and kidney literature"
---
## Execution Protocol
1. Resolve 2-4 compound names or `#1`/`#2` from session ledger and call `compare_compounds`.
2. Batch `search_literature` + `search_clinical_trials` on the top 2 compared compounds (reuse ledger if already audited).

## Fixed Output Format (Cohesive Academic Prose — No Mechanical Bullet Listing)
### 1. Head-to-Head Safety & Clinical Maturity
Summarize clinical readiness and kidney safety in 2 sentences plus a compact Markdown table (`Compound | Phase | MoA | T-DIKI | DIRIL | ECM_fibrosis | Podocyte_slit`).
### 2. Mechanistic & Renal Module Trade-offs
Write one cohesive paragraph contrasting anti-fibrotic (`ECM_fibrosis`, `TGFb_SMAD`), podocyte/metabolic (`Podocyte_slit`, `PT_FAO_mito`), and PROGENy pathway strengths across the compared drugs.
### 3. Integrated Literature & Clinical Review
Write **two cohesive prose paragraphs** directly contrasting the compared drugs: Paragraph 1 compares published kidney efficacy depth and novelty (`[PMID:<digits>]`); Paragraph 2 contrasts nephrotoxicity reports (`[PMID:<digits>]`) and clinical trial maturity (`[NCT<8-digits>]`).
### 4. Context-Dependent Recommendation
Write 2 crisp sentences stating which drug wins for safety vs. anti-fibrotic efficacy and your recommended lead. Do NOT write a manual References section (auto-appended). Never invent IDs or numbers.
