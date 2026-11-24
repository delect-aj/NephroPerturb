---
id: compound-compare
name: Head-to-Head Compound Comparison
short_label: Drug Comparison
description: Compare 2-4 compounds side-by-side across nephrotoxicity risk, PROGENy signaling pathways, 9 renal pathology modules, and clinical literature.
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
1. Resolve 2-4 compound names or `#1`/`#2` references from session memory and call `compare_compounds`.
2. Batch `search_literature` + `search_clinical_trials` on the top 2 compared compounds (reusing session records if already retrieved).

## Fixed Output Format (Natural Biomedical Prose — Never Print Raw JSON Variable Names like `tdiki_tier` or `diril_label`)
### 1. Head-to-Head Safety & Clinical Maturity
Summarize clinical development stage and predicted nephrotoxicity risk in 2 sentences, followed by a compact Markdown table (`Compound | Phase | MoA | T-DIKI | DIRIL | ECM_fibrosis | Podocyte_slit`).
### 2. Mechanistic & Renal Module Trade-offs
Write one cohesive paragraph contrasting anti-fibrotic activity (`ECM_fibrosis`, `TGFb_SMAD`), podocyte and tubular metabolic preservation (`Podocyte_slit`, `PT_FAO_mito`), and PROGENy signaling pathways across the compared compounds.
### 3. Integrated Literature & Clinical Review
Write **two cohesive prose paragraphs** directly contrasting the compared drugs: Paragraph 1 compares published kidney efficacy studies and repurposing novelty (`[PMID:<digits>]`); Paragraph 2 contrasts documented nephrotoxicity (`[PMID:<digits>]`) and clinical trial maturity (`[NCT<8-digits>]`).
### 4. Context-Dependent Recommendation
Write 2 concise sentences stating which compound is preferable for renal safety versus anti-fibrotic potency and naming your recommended lead. Do NOT write a manual References section (auto-appended). Never invent identifiers or numbers.
