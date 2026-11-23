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
  - Target Renal Expression & Direct Drugs
  - Top Knockdown-Mimicking Leads
  - Lead Safety & Kidney Evidence
example_prompt: "Analyze TGFBR1 in kidney disease: check nephron expression, top knockdown-mimicking drugs, lead safety, and literature evidence"
---
## Execution Protocol (Strictly Deterministic & Token-Lean)
1. **Target Profile**: Call `profile_target` for the target gene symbol to inspect nephron compartment expression, direct targeting drugs, and top knockdown-mimicking compounds.
2. **Lead Safety Check**: Pick the #1 named mimicking compound (or direct approved drug if available) and call `profile_compound` to verify `tdiki_tier`, `diril_label`, and `clinical_phase`.
3. **Evidence Check**: Call `search_literature` on the target gene (`<symbol>`) in kidney disease AND on the top mimicking compound (`include_safety=true`), plus `search_clinical_trials` on the top compound if it is a named drug.
4. **Stop & Synthesize**: Concisely summarize target localization, direct vs. mimicking hits, lead NephroSafe profile, and grounded `[PMID:<id>]` / `[NCT<id>]` evidence in <= 200 words.
