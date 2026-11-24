---
id: target-to-lead
name: Target-to-Lead & Genetic Mimicry
short_label: Target & Mimicry
description: Integrate nephron segment expression, shRNA/CRISPR knockdown mimicry, lead safety evaluation, and PubMed target evidence.
color: "#d97706"
max_steps: 5
allowed_tools:
  - profile_target
  - profile_compound
  - search_literature
  - search_clinical_trials
requires_literature: true
output_sections:
  - "1. Target Nephron Biology & Direct Drugs"
  - "2. Knockdown-Mimicking Leads & Safety"
  - "3. Integrated Literature & Clinical Review"
  - "4. Translational Recommendation & Next Steps"
example_prompt: "Analyze TGFBR1 in kidney disease: check nephron expression, top knockdown-mimicking drugs, lead safety, and literature evidence"
---
## Execution Protocol
1. Call `profile_target` for the target gene symbol.
2. Call `profile_compound` using the **exact `pert_id`** of the #1 named knockdown-mimicking compound to evaluate its renal safety.
3. Batch `search_literature` on the target gene AND `search_literature` + `search_clinical_trials` on the top mimicking lead.

## Fixed Output Format (Natural Biomedical Prose — Never Print Raw JSON Variable Names like `tdiki_tier` or `sc_pt`)
### 1. Target Nephron Biology & Direct Drugs
Write one concise paragraph summarizing the target gene's expression across kidney compartments and any curated direct-targeting compounds.
### 2. Knockdown-Mimicking Leads & Safety
Present the top 3 knockdown-mimicking compounds in a compact Markdown table (`Rank | Compound | pert_id | Cosine`) and explain the #1 lead's mechanism of action, signaling pathway effects, and predicted nephrotoxicity profile in 2-3 clear sentences.
### 3. Integrated Literature & Clinical Review
Write **two cohesive prose paragraphs**: Paragraph 1 summarizes the target gene's established role in renal pathophysiology (`[PMID:<digits>]`); Paragraph 2 evaluates the lead compound's published kidney efficacy, renal safety record (`[PMID:<digits>]`), and clinical trials (`[NCT<8-digits>]`).
### 4. Translational Recommendation & Next Steps
Write 2 concise sentences prioritizing the strongest validation compound and proposing a relevant functional assay. Do NOT write a manual References section (auto-appended). Never invent identifiers or numbers.
