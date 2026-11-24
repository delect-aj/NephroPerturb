---
id: structure-moa-evidence
name: Structure Similarity & MoA Validation
short_label: Structure & MoA
description: Search 21,299 ECFP4 molecular fingerprints by SMILES or compound ID, infer mechanism of action, evaluate renal safety, and review literature.
color: "#4f46e5"
max_steps: 4
allowed_tools:
  - find_safe_analogs
  - profile_compound
  - search_literature
requires_literature: true
output_sections:
  - "1. Chemical Neighborhood & Consensus MoA"
  - "2. Closest Neighbor Safety & Kidney Profile"
  - "3. Integrated Literature & Clinical Review"
  - "4. Translational Recommendation & Next Steps"
example_prompt: "Find structural analogs to CC(=O)OC1=CC=CC=C1C(=O)O, infer MoA and NephroSafe risk, and check kidney literature for the top neighbor"
---
## Execution Protocol
1. Call `find_safe_analogs` using the provided `smiles` or `compound`.
2. Call `profile_compound` using the **exact `pert_id`** of the closest named/MoA-annotated structural neighbor.
3. Call `search_literature(entity=<neighbor name>, include_safety=true)` on that neighbor.

## Fixed Output Format (Natural Biomedical Prose — Never Print Raw JSON Variable Names like `consensus_moa` or `tdiki_tier`)
### 1. Chemical Neighborhood & Consensus MoA
State the inferred consensus mechanism of action across the chemical neighborhood and summarize the top 3 structural neighbors in a compact Markdown table (`Rank | Compound | pert_id | Tanimoto | T-DIKI | MoA`).
### 2. Closest Neighbor Safety & Kidney Profile
Write one flowing paragraph describing the molecular targets, signaling pathways, renal pathology modules, predicted T-DIKI nephrotoxicity probability, and FDA DIRIL classification of the closest profiled neighbor.
### 3. Integrated Literature & Clinical Review
Write **one to two cohesive prose paragraphs** synthesizing the neighbor's published renal efficacy and safety findings with inline `[PMID:<digits>]` citations, noting whether kidney evidence is well established or unexplored.
### 4. Translational Recommendation & Next Steps
Write 2 concise sentences on the expected pharmacological profile and the safest direction for scaffold optimization. Do NOT write a manual References section (auto-appended). Never invent identifiers or numbers.
