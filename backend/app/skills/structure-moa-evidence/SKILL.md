---
id: structure-moa-evidence
name: Structure Similarity & MoA Validation
short_label: Structure -> MoA
description: Scan 21,299 ECFP4 fingerprints by SMILES or compound ID, infer consensus MoA, audit safety, and check literature support.
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
2. Call `profile_compound` using the **exact `pert_id`** of the closest named/MoA-annotated neighbor.
3. Call `search_literature(entity=<neighbor name>, include_safety=true)` on that neighbor.

## Fixed Output Format (Cohesive Academic Prose — No Mechanical Bullet Listing)
### 1. Chemical Neighborhood & Consensus MoA
State the inferred `consensus_moa` and summarize Top-3 neighbors in a compact Markdown table (`Rank | Compound | pert_id | Tanimoto | T-DIKI | MoA`).
### 2. Closest Neighbor Safety & Kidney Profile
Write one flowing paragraph covering targets, PROGENy/renal modules, T-DIKI probability, and DIRIL status of the profiled neighbor.
### 3. Integrated Literature & Clinical Review
Write **one to two cohesive prose paragraphs** synthesizing the neighbor's renal efficacy findings and nephrotoxicity warnings from retrieved paper `takeaway`s with inline `[PMID:<digits>]` citations, noting whether kidney evidence is well-established or novel.
### 4. Translational Recommendation & Next Steps
Write 2 crisp sentences on predicted pharmacology and safest scaffold direction. Do NOT write a manual References section (auto-appended). Never invent IDs or numbers.
