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
  - Chemical Neighbors & Consensus MoA
  - NephroSafe Risk across Analogs
  - Kidney Literature Support
example_prompt: "Find structural analogs to CC(=O)OC1=CC=CC=C1C(=O)O, infer MoA and NephroSafe risk, and check kidney literature for the top neighbor"
---
## Execution Protocol (Strictly Deterministic & Token-Lean)
1. **ECFP4 Scan**: Call `find_safe_analogs` using the provided `smiles` or `compound` (keep `max_diki_tier` unset unless user requested low-toxicity filtering).
2. **Profile Closest Annotated Neighbor**: Select the top neighbor with an annotated MoA (or #1 hit) and call `profile_compound` to obtain targets, PROGENy pathways, T-DIKI tier, and DIRIL label.
3. **Literature Validation**: Call `search_literature` on the top named neighbor with `disease_context="kidney disease"`.
4. **Stop & Synthesize**: Report consensus MoA, top Tanimoto neighbors with T-DIKI safety tiers, and grounded `[PMID:<id>]` literature in <= 180 words.
