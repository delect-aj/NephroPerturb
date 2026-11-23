---
id: target-to-lead
name: Target-to-Lead & Genetic Mimicry
short_label: Target -> Lead
description: Combine nephron compartment expression, shRNA/CRISPR knockdown mimicry, lead safety check, and PubMed target evidence.
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
2. Call `profile_compound` using the **exact `pert_id`** of the #1 named mimicking compound to audit T-DIKI & DIRIL.
3. Batch `search_literature` on the target gene AND `search_literature` + `search_clinical_trials` on the top mimicking lead.

## Fixed Output Format (Cohesive Academic Prose — No Mechanical Bullet Listing)
### 1. Target Nephron Biology & Direct Drugs
Write one concise paragraph summarizing nephron compartment expression and direct targeting drugs.
### 2. Knockdown-Mimicking Leads & Safety
Present Top-3 mimicking compounds in a compact Markdown table (`Rank | Compound | pert_id | Cosine`) and explain the profiled #1 lead's MoA, pathways, and NephroSafe T-DIKI/DIRIL status in 2-3 sentences.
### 3. Integrated Literature & Clinical Review
Write **two cohesive prose paragraphs** weaving together paper `takeaway`s: Paragraph 1 summarizes the target's established kidney role (`[PMID:<digits>]`); Paragraph 2 evaluates the #1 lead's kidney efficacy, nephrotoxicity reports (`[PMID:<digits>]`), and clinical trials (`[NCT<8-digits>]`).
### 4. Translational Recommendation & Next Steps
Write 2 crisp sentences prioritizing the strongest validation lead and experimental assay. Do NOT write a manual References section (auto-appended). Never invent IDs or numbers.
