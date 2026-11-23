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
  - "1. Structural Neighbors & Consensus MoA"
  - "2. Top Neighbor Safety & Kidney Profile"
  - "3. Literature & Clinical Synthesis"
  - "4. Actionable Recommendation"
example_prompt: "Find structural analogs to CC(=O)OC1=CC=CC=C1C(=O)O, infer MoA and NephroSafe risk, and check kidney literature for the top neighbor"
---
## Execution Protocol
1. Call `find_safe_analogs` using the provided `smiles` or `compound`.
2. Call `profile_compound` using the **exact `pert_id`** of the closest named/MoA-annotated neighbor.
3. Call `search_literature(entity=<neighbor name>, include_safety=true)` on that top neighbor.

## Fixed Output Format (Use Exact Headings)
### 1. Structural Neighbors & Consensus MoA
Report inferred `consensus_moa` and Top-3 analogs (`pert_id`, Tanimoto, T-DIKI tier, phase).
### 2. Top Neighbor Safety & Kidney Profile
Summarize targets, key PROGENy/renal modules, T-DIKI probability, and DIRIL status of the profiled neighbor.
### 3. Literature & Clinical Synthesis
Synthesize the neighbor's retrieved paper `takeaway`s cleanly (**Evidence Verdict**, **Efficacy Findings** with `[PMID:<digits>]`, **Safety Signals** with `[PMID:<digits>]`, and novelty standing).
### 4. Actionable Recommendation
State predicted pharmacological MoA and safest chemical starting point. Never invent PMIDs, BRDs, or numbers.
