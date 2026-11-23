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
  - "1. Target Renal Expression & Direct Drugs"
  - "2. Knockdown-Mimicking Leads & Safety"
  - "3. Literature & Clinical Synthesis"
  - "4. Actionable Recommendation"
example_prompt: "Analyze TGFBR1 in kidney disease: check nephron expression, top knockdown-mimicking drugs, lead safety, and literature evidence"
---
## Execution Protocol
1. Call `profile_target` for the target gene symbol.
2. Pick the #1 named mimicking compound using its **exact `pert_id`** and call `profile_compound` to audit T-DIKI & DIRIL.
3. Batch `search_literature` on the target gene AND `search_literature` + `search_clinical_trials` on the top mimicking lead.

## Fixed Output Format (Use Exact Headings)
### 1. Target Renal Expression & Direct Drugs
Summarize compartment expression and count/names of direct targeting drugs.
### 2. Knockdown-Mimicking Leads & Safety
List Top-3 mimicking compounds (cosine similarity, `pert_id`) and full NephroSafe T-DIKI / DIRIL verdict of the profiled #1 lead.
### 3. Literature & Clinical Synthesis
Synthesize paper `takeaway`s for both target biology and the #1 lead into concise bullets covering **Evidence Verdict & Novelty**, **Kidney Findings** (`[PMID:<digits>]`), **Nephrotoxicity Signals** (`[PMID:<digits>]`), and **Clinical Trials** (`[NCT<8-digits>]`).
### 4. Actionable Recommendation
State strongest validation lead and experimental next step. Never invent PMIDs, NCTs, BRDs, or numbers.
