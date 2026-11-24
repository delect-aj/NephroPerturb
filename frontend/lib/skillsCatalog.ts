export interface SkillStepDoc {
  step: number;
  title: string;
  tools: string[];
  logic: string;
}

export interface SkillLogicDoc {
  id: string;
  shortLabel: string;
  name: string;
  color: string;
  maxSteps: number;
  whenUsed: string;
  allowedTools: string[];
  workflow: SkillStepDoc[];
  outputSections: string[];
  examplePrompt: string;
}

export const AUTO_ROUTING_RULES = [
  {
    priority: "1",
    title: "Manual Skill Selection",
    rule: "If you click a specific Skill pill in the console, Auto routing is skipped and that Skill runs directly.",
  },
  {
    priority: "2",
    title: "Compare & Safety Rescue",
    rule: "Keywords like compare/vs trigger Compare Drugs; nephrotoxic/safer analogs/T-DIKI/DIRIL trigger Safety & Rescue.",
  },
  {
    priority: "3",
    title: "Literature & Session Follow-ups",
    rule: "Pure PubMed/clinical trial queries (or follow-ups referencing #1, #2, or prior candidates) route to Literature & Trials.",
  },
  {
    priority: "4",
    title: "Deterministic SOP-1 to SOP-6 & Guardrail",
    rule: "Remaining queries match Up/Down genes, cohorts (DKD/LN/IgAN/AKI), pathways, target knockdowns, or SMILES scaffolds; non-kidney topics are stopped safely.",
  },
];

export const SKILLS_CATALOG: SkillLogicDoc[] = [
  {
    id: "disease-repurposing",
    shortLabel: "Disease -> Evidence",
    name: "Disease-to-Evidence Repurposing",
    color: "#2563eb",
    maxSteps: 6,
    whenUsed: "Kidney cohorts (DKD, LN, IgAN, AKI), Up/Down gene signatures, or Pathway/TF screens.",
    allowedTools: [
      "run_cohort_case",
      "score_gene_signature",
      "query_pathway_tf",
      "profile_compound",
      "find_safe_analogs",
      "search_literature",
      "search_clinical_trials",
    ],
    workflow: [
      {
        step: 1,
        title: "Screen Drug Candidates",
        tools: ["run_cohort_case", "score_gene_signature", "query_pathway_tf"],
        logic: "Ranks 21,299 compounds by transcriptional disease-reversal and inspects Top-3 hits for High T-DIKI or FDA DIRIL+ toxicity flags.",
      },
      {
        step: 2,
        title: "Auto-Rescue Toxic Top Hits",
        tools: ["re-screen (Low T-DIKI)", "find_safe_analogs"],
        logic: "Runs automatically only if a Top-3 lead is flagged toxic, switching to approved Low T-DIKI drugs or safer structural analogs.",
      },
      {
        step: 3,
        title: "Deep-Profile #1 Safe Lead",
        tools: ["profile_compound"],
        logic: "Fetches the #1 safe compound by exact pert_id to examine its targets, MoA, PROGENy pathways, 9 renal modules, and K-PRL genes.",
      },
      {
        step: 4,
        title: "Verify Literature & Trials",
        tools: ["search_literature", "search_clinical_trials"],
        logic: "Queries Europe PMC / PubMed (Title/Abstract for both efficacy and nephrotoxicity) plus ClinicalTrials.gov for the Top 1-2 leads, then writes the verified report.",
      },
    ],
    outputSections: [
      "1. Executive Synthesis & Prioritized Candidates",
      "2. Mechanistic & NephroSafe Rationale",
      "3. Integrated Literature & Clinical Review",
      "4. Translational Recommendation & Next Steps",
    ],
    examplePrompt:
      "Find reversal drugs for the DKD glomeruli case, auto-filter High T-DIKI hits if needed, and verify literature & clinical trials for top candidates",
  },
  {
    id: "toxicity-rescue",
    shortLabel: "Safety & Rescue",
    name: "Compound Safety & Toxicity Rescue",
    color: "#dc2626",
    maxSteps: 5,
    whenUsed: "Checking a compound safety profile, T-DIKI risk drivers, or safer Low-DIKI structural analogs.",
    allowedTools: [
      "profile_compound",
      "explain_tdiki",
      "find_safe_analogs",
      "search_literature",
      "search_clinical_trials",
    ],
    workflow: [
      {
        step: 1,
        title: "Audit Risk & Attribution Drivers",
        tools: ["profile_compound", "explain_tdiki"],
        logic: "Computes NephroSafe T-DIKI v2 tier/probability, FDA DIRIL label, and the structural and transcriptomic features driving toxicity.",
      },
      {
        step: 2,
        title: "Scan Safer ECFP4 Analogs",
        tools: ["find_safe_analogs"],
        logic: "Triggered when risk is Moderate/High, DIRIL+, or alternatives are requested; inspects the top 120 ECFP4 neighbors to keep distinct Low T-DIKI analogs.",
      },
      {
        step: 3,
        title: "Check Toxicity Literature & Trials",
        tools: ["search_literature", "search_clinical_trials"],
        logic: "Collects published nephrotoxicity mechanisms alongside kidney clinical trial records for the queried drug.",
      },
      {
        step: 4,
        title: "Build Risk & Substitution Plan",
        tools: ["grounded synthesis"],
        logic: "Synthesizes attribution drivers, analog count/availability, and literature into actionable risk mitigation or scaffold replacement advice.",
      },
    ],
    outputSections: [
      "1. NephroSafe Verdict & Attribution Rationale",
      "2. Safer Structural Analog Rescue",
      "3. Integrated Literature & Clinical Review",
      "4. Translational Recommendation & Next Steps",
    ],
    examplePrompt:
      "Is tacrolimus nephrotoxic? Explain T-DIKI drivers, audit safety literature, and find safer Low-DIKI structural analogs",
  },
  {
    id: "target-to-lead",
    shortLabel: "Target -> Lead",
    name: "Target-to-Lead & Genetic Mimicry",
    color: "#d97706",
    maxSteps: 5,
    whenUsed: "Target gene biology, single-cell nephron localization, and shRNA/CRISPR knockdown-mimicking drugs.",
    allowedTools: [
      "profile_target",
      "profile_compound",
      "search_literature",
      "search_clinical_trials",
    ],
    workflow: [
      {
        step: 1,
        title: "Map Nephron Expression & Mimics",
        tools: ["profile_target"],
        logic: "Retrieves target expression across kidney compartments, direct drugs, and compounds whose signatures mimic genetic knockdown.",
      },
      {
        step: 2,
        title: "Safety Check Top Mimic Lead",
        tools: ["profile_compound"],
        logic: "Profiles the #1 named mimicking compound by exact pert_id to check MoA, renal pathways, and T-DIKI / DIRIL kidney safety.",
      },
      {
        step: 3,
        title: "Query Target & Lead Evidence",
        tools: ["search_literature", "search_clinical_trials"],
        logic: "Searches Title/Abstract PubMed papers for both the target gene and the #1 lead compound, plus any registered kidney trials.",
      },
      {
        step: 4,
        title: "Prioritize Validation Strategy",
        tools: ["grounded synthesis"],
        logic: "Combines target biology, knockdown mimicry, safety audit, and literature into a focused validation recommendation.",
      },
    ],
    outputSections: [
      "1. Target Nephron Biology & Direct Drugs",
      "2. Knockdown-Mimicking Leads & Safety",
      "3. Integrated Literature & Clinical Review",
      "4. Translational Recommendation & Next Steps",
    ],
    examplePrompt:
      "Analyze TGFBR1 in kidney disease: check nephron expression, top knockdown-mimicking drugs, lead safety, and literature evidence",
  },
  {
    id: "structure-moa-evidence",
    shortLabel: "Structure -> MoA",
    name: "Structure Similarity & MoA Validation",
    color: "#4f46e5",
    maxSteps: 4,
    whenUsed: "Querying a SMILES string, chemical structure similarity, or a BRD-... compound ID.",
    allowedTools: [
      "find_safe_analogs",
      "profile_compound",
      "search_literature",
    ],
    workflow: [
      {
        step: 1,
        title: "Scan 2D Chemical Neighbors",
        tools: ["find_safe_analogs"],
        logic: "Computes 2048-bit ECFP4 Tanimoto similarity across 21,299 compounds and derives the dominant consensus_moa.",
      },
      {
        step: 2,
        title: "Profile Closest Annotated Neighbor",
        tools: ["profile_compound"],
        logic: "Audits the nearest named neighbor (by exact pert_id) for targets, PROGENy pathways, 9 renal modules, and T-DIKI / DIRIL risk.",
      },
      {
        step: 3,
        title: "Check Neighbor Kidney Literature",
        tools: ["search_literature"],
        logic: "Retrieves renal efficacy and toxicity publications on the closest neighbor to distinguish known biology from novel scaffolds.",
      },
      {
        step: 4,
        title: "Summarize MoA & Scaffold Advice",
        tools: ["grounded synthesis"],
        logic: "Integrates Tanimoto similarity, inferred MoA, safety profile, and literature into scaffold optimization guidance.",
      },
    ],
    outputSections: [
      "1. Chemical Neighborhood & Consensus MoA",
      "2. Closest Neighbor Safety & Kidney Profile",
      "3. Integrated Literature & Clinical Review",
      "4. Translational Recommendation & Next Steps",
    ],
    examplePrompt:
      "Find compounds structurally similar to CC(=O)OC1=CC=CC=C1C(=O)O and infer MoA & kidney safety",
  },
  {
    id: "literature-evidence",
    shortLabel: "Literature & Trials",
    name: "Literature & Clinical Trial Evidence Synthesis",
    color: "#0284c7",
    maxSteps: 5,
    whenUsed: "Pure literature/clinical trial checks, novelty audits, or follow-ups on #1 / #2 session candidates.",
    allowedTools: [
      "search_literature",
      "search_clinical_trials",
      "profile_compound",
    ],
    workflow: [
      {
        step: 1,
        title: "Resolve Target Entities & Context",
        tools: ["session memory"],
        logic: "Resolves up to 2 named drugs/genes or #1/#2 ordinals from active session memory while preserving disease context.",
      },
      {
        step: 2,
        title: "Bidirectional Title/Abstract Search",
        tools: ["search_literature"],
        logic: "Runs separate kidney efficacy and nephrotoxicity queries in Europe PMC / PubMed and classifies evidence tier & novelty.",
      },
      {
        step: 3,
        title: "Fetch Trials & Missing Risk Score",
        tools: ["search_clinical_trials", "profile_compound"],
        logic: "Collects ClinicalTrials.gov kidney studies (phase/status) and fills in T-DIKI / DIRIL safety scores when missing.",
      },
      {
        step: 4,
        title: "Synthesize Cohesive Review",
        tools: ["grounded synthesis"],
        logic: "Weaves paper takeaways, toxicity warnings, and trial status into prose with auto-verified numbered References.",
      },
    ],
    outputSections: [
      "1. Executive Evidence Verdict & Novelty",
      "2. Synthesized Kidney Efficacy Literature",
      "3. Integrated Nephrotoxicity & Clinical Trials Review",
      "4. Translational Takeaway",
    ],
    examplePrompt:
      "Profile dexamethasone and summarize its renal literature & clinical trials",
  },
  {
    id: "compound-compare",
    shortLabel: "Compare Drugs",
    name: "Head-to-Head Compound Comparison",
    color: "#0d9488",
    maxSteps: 5,
    whenUsed: "Comparing 2-4 compounds side-by-side (e.g., Compare drug A and drug B, or Compare #1 and #2).",
    allowedTools: [
      "compare_compounds",
      "search_literature",
      "search_clinical_trials",
    ],
    workflow: [
      {
        step: 1,
        title: "Build Multi-Metric Matrix",
        tools: ["compare_compounds"],
        logic: "Aligns 2-4 drugs across clinical phase, MoA, T-DIKI v2, FDA DIRIL, PROGENy pathways, and 9 renal pathology modules.",
      },
      {
        step: 2,
        title: "Audit Top-2 Literature & Trials",
        tools: ["search_literature", "search_clinical_trials"],
        logic: "Fetches kidney efficacy, safety papers, and trial phases for the top two compared drugs (reusing prior session results if cached).",
      },
      {
        step: 3,
        title: "Contrast Mechanistic Trade-offs",
        tools: ["grounded synthesis"],
        logic: "Directly contrasts anti-fibrotic potency, podocyte/FAO preservation, nephrotoxicity risk, and clinical maturity.",
      },
      {
        step: 4,
        title: "Deliver Context Verdict",
        tools: ["grounded synthesis"],
        logic: "States clearly which compound leads on kidney safety vs. efficacy and recommends the better translational fit.",
      },
    ],
    outputSections: [
      "1. Head-to-Head Safety & Clinical Maturity",
      "2. Mechanistic & Renal Module Trade-offs",
      "3. Integrated Literature & Clinical Review",
      "4. Context-Dependent Recommendation",
    ],
    examplePrompt:
      "Compare dexamethasone and losartan head-to-head on renal fibrosis modules, podocyte protection, T-DIKI safety, and kidney literature",
  },
];
