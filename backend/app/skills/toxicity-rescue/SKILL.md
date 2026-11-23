---
id: toxicity-rescue
name: Compound Safety & Toxicity Rescue
short_label: Safety & Rescue
description: Audit a drug's kidney toxicity (T-DIKI v2 + DIRIL), explain attribution drivers, and rescue with safer Low-DIKI structural analogs.
color: "#dc2626"
max_steps: 5
allowed_tools:
  - profile_compound
  - explain_tdiki
  - find_safe_analogs
  - search_literature
  - search_clinical_trials
requires_literature: true
output_sections:
  - NephroSafe Safety Verdict
  - T-DIKI Attribution & K-PRL Drivers
  - Safer Structural Analogs
  - Clinical & Literature Audit
example_prompt: "Is tacrolimus nephrotoxic? Explain its T-DIKI drivers, check nephrotoxicity literature, and find safer Low T-DIKI analogs"
---
## Execution Protocol (Strictly Deterministic & Token-Lean)
1. **Profile Compound**: Call `profile_compound` for the target compound (or session token) to inspect `tdiki_tier`, `tdiki_prob`, `diril_label`, `clinical_phase`, MoA, and K-PRL signature.
2. **Attribution**: Call `explain_tdiki` to retrieve the exact structural/transcriptomic risk drivers.
3. **Rescue Search**: If `tdiki_tier` is `"High"` or `"Moderate"`, OR `diril_label == 1`, OR the user asked for analogs/alternatives, call `find_safe_analogs(compound=..., max_diki_tier="Low", top_k=10)` to identify structurally similar low-risk candidates.
4. **Safety Literature & Trials**: Call `search_literature(entity=<compound>, include_safety=true)` (and `search_clinical_trials` if time permits or requested).
5. **Stop & Synthesize**: Write <= 200 words stating the safety verdict, top attribution drivers, best safer analog(s) with Tanimoto & T-DIKI tier, and grounded `[PMID:<id>]` / `[NCT<id>]` evidence. Never invent numbers or citations.
