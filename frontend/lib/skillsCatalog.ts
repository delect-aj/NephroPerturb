export interface SkillStepDoc {
  step: number;
  title: string;
  tools: string[];
  stageTag?: "Compute" | "Auto-Reflect" | "Evidence" | "Verify & Write";
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

export const SHARED_SAFEGUARDS = [
  {
    title: "Scoped Determinism",
    detail: "DeepSeek ReAct runs at temperature=0.0, seed=42, restricted strictly to each Skill's allowed tools and step cap.",
  },
  {
    title: "7-Day Evidence Cache",
    detail: "Title/Abstract Europe PMC (PubMed fallback) and ClinicalTrials.gov v2 queries are cached for 7 days in SQLite.",
  },
  {
    title: "Grounding Verifier",
    detail: "Audits every PMID, NCT, BRD ID, and score against live tool outputs with 1x surgical repair or deterministic fallback.",
  },
  {
    title: "Auto-Built References",
    detail: "Numbered bibliography entries and table footnotes are assembled directly from verified tool metadata with zero extra tokens.",
  },
];

export const SKILLS_CATALOG: SkillLogicDoc[] = [
  {
    id: "disease-repurposing",
    shortLabel: "Disease -> Evidence",
    name: "Disease-to-Evidence Repurposing",
    color: "#2563eb",
    maxSteps: 6,
    whenUsed: "10 kidney cohorts (DKD, LN, IgAN, CKD, AKI), Up/Down gene signatures, or Pathway/TF modulation screens.",
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
        title: "Screen Candidates",
        tools: ["run_cohort_case", "score_gene_signature", "query_pathway_tf"],
        stageTag: "Compute",
        logic: "Ranks 21,299 compounds for kidney disease reversal and checks Top-3 hits for High T-DIKI or FDA DIRIL+ risk.",
      },
      {
        step: 2,
        title: "Auto-Rescue Toxic Top Hits",
        tools: ["find_safe_analogs"],
        stageTag: "Auto-Reflect",
        logic: "Triggered automatically if any Top-3 hit is High T-DIKI or DIRIL+: re-screens approved Low T-DIKI drugs or safer structural analogs.",
      },
      {
        step: 3,
        title: "Deep-Profile #1 Safe Lead",
        tools: ["profile_compound"],
        stageTag: "Compute",
        logic: "Profiles the #1 safe lead by exact pert_id (BRD-...) for targets, MoA, PROGENy pathways, 9 renal modules, and K-PRL genes.",
      },
      {
        step: 4,
        title: "Audit Literature & Trials",
        tools: ["search_literature", "search_clinical_trials"],
        stageTag: "Evidence",
        logic: "Batches Title/Abstract Europe PMC/PubMed (efficacy + safety) and ClinicalTrials.gov on the Top 1-2 leads, then writes the verified 4-section report.",
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
    whenUsed: "Auditing a drug's kidney safety, inspecting T-DIKI attribution drivers, or rescuing toxic drugs with safer analogs.",
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
        title: "Audit Risk & Attribution",
        tools: ["profile_compound", "explain_tdiki"],
        stageTag: "Compute",
        logic: "Computes T-DIKI v2 tier/probability, FDA DIRIL status, and the structural and transcriptomic drivers behind kidney toxicity.",
      },
      {
        step: 2,
        title: "Scan Safer ECFP4 Analogs",
        tools: ["find_safe_analogs"],
        stageTag: "Auto-Reflect",
        logic: "If risk is Moderate/High, DIRIL+, or alternatives are requested, scans top 120 ECFP4 neighbors and retains distinct Low T-DIKI analogs.",
      },
      {
        step: 3,
        title: "Review Toxicity Literature & Trials",
        tools: ["search_literature", "search_clinical_trials"],
        stageTag: "Evidence",
        logic: "Collects published nephrotoxicity mechanisms alongside registered kidney clinical trials for the queried compound.",
      },
      {
        step: 4,
        title: "Synthesize Risk Mitigation",
        tools: [],
        stageTag: "Verify & Write",
        logic: "Audits all IDs and scores, then outputs a 4-section safety verdict advising on monitoring, analog rescue, or scaffold switch.",
      },
    ],
    outputSections: [
      "1. NephroSafe Verdict & Attribution Rationale",
      "2. Safer Structural Analog Rescue",
      "3. Integrated Literature & Clinical Review",
      "4. Translational Recommendation & Next Steps",
    ],
    examplePrompt:
      "Is tacrolimus nephrotoxic? Explain its T-DIKI drivers, check nephrotoxicity literature, and find safer Low T-DIKI analogs",
  },
  {
    id: "target-to-lead",
    shortLabel: "Target -> Lead",
    name: "Target-to-Lead & Genetic Mimicry",
    color: "#d97706",
    maxSteps: 5,
    whenUsed: "Evaluating a kidney target gene, single-cell nephron expression, and shRNA/CRISPR knockdown-mimicking drugs.",
    allowedTools: [
      "profile_target",
      "profile_compound",
      "search_literature",
      "search_clinical_trials",
    ],
    workflow: [
      {
        step: 1,
        title: "Map Nephron Biology & Mimics",
        tools: ["profile_target"],
        stageTag: "Compute",
        logic: "Retrieves nephron compartment expression, direct targeting drugs, and compounds whose signatures mimic genetic knockdown.",
      },
      {
        step: 2,
        title: "Check #1 Mimic Lead Safety",
        tools: ["profile_compound"],
        stageTag: "Compute",
        logic: "Profiles the #1 named knockdown-mimicking compound by exact pert_id to verify MoA, pathways, and T-DIKI/DIRIL safety.",
      },
      {
        step: 3,
        title: "Audit Target & Lead Evidence",
        tools: ["search_literature", "search_clinical_trials"],
        stageTag: "Evidence",
        logic: "Searches Title/Abstract PubMed for both the target gene and the #1 lead compound, plus kidney clinical trials for the lead.",
      },
      {
        step: 4,
        title: "Prioritize Validation Assay",
        tools: [],
        stageTag: "Verify & Write",
        logic: "Verifies every score and citation, then recommends the top validation lead and next experimental assay.",
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
    whenUsed: "Submitting a SMILES string, chemical similarity query, or BRD-... scaffold ID to infer MoA and safety.",
    allowedTools: [
      "find_safe_analogs",
      "profile_compound",
      "search_literature",
    ],
    workflow: [
      {
        step: 1,
        title: "Scan ECFP4 Chemical Space",
        tools: ["find_safe_analogs"],
        stageTag: "Compute",
        logic: "Computes 2048-bit ECFP4 Tanimoto similarity across 21,299 compounds and infers the dominant consensus_moa.",
      },
      {
        step: 2,
        title: "Profile Nearest Annotated Neighbor",
        tools: ["profile_compound"],
        stageTag: "Compute",
        logic: "Audits the closest named neighbor (by exact pert_id) for targets, PROGENy pathways, renal modules, and T-DIKI/DIRIL status.",
      },
      {
        step: 3,
        title: "Check Neighbor Kidney Literature",
        tools: ["search_literature"],
        stageTag: "Evidence",
        logic: "Queries Europe PMC/PubMed (efficacy + nephrotoxicity) for the closest neighbor to separate known biology from novel scaffolds.",
      },
      {
        step: 4,
        title: "Report MoA & Scaffold Guidance",
        tools: [],
        stageTag: "Verify & Write",
        logic: "Verifies neighbor scores and PMIDs, then summarizes inferred pharmacology and the safest scaffold direction.",
      },
    ],
    outputSections: [
      "1. Chemical Neighborhood & Consensus MoA",
      "2. Closest Neighbor Safety & Kidney Profile",
      "3. Integrated Literature & Clinical Review",
      "4. Translational Recommendation & Next Steps",
    ],
    examplePrompt:
      "Find structural analogs to CC(=O)OC1=CC=CC=C1C(=O)O, infer MoA and NephroSafe risk, and check kidney literature for the top neighbor",
  },
  {
    id: "literature-evidence",
    shortLabel: "Literature & Trials",
    name: "Bidirectional Literature & Clinical Audit",
    color: "#0284c7",
    maxSteps: 5,
    whenUsed: "Pure PubMed/clinical-trial audits, novelty checks, or multi-turn follow-ups referencing #1 / #2 candidates.",
    allowedTools: [
      "search_literature",
      "search_clinical_trials",
      "profile_compound",
    ],
    workflow: [
      {
        step: 1,
        title: "Resolve Entities & Disease Context",
        tools: [],
        stageTag: "Compute",
        logic: "Resolves up to 2 named drugs/genes or #1/#2 references from active session memory while preserving the active kidney disease context.",
      },
      {
        step: 2,
        title: "Bidirectional Title/Abstract Search",
        tools: ["search_literature"],
        stageTag: "Evidence",
        logic: "Runs separate kidney efficacy and nephrotoxicity searches in Europe PMC/PubMed and assigns evidence tier and novelty.",
      },
      {
        step: 3,
        title: "Fetch Trials & Safety Baseline",
        tools: ["search_clinical_trials", "profile_compound"],
        stageTag: "Evidence",
        logic: "Retrieves ClinicalTrials.gov kidney studies (phase/status) and profiles T-DIKI/DIRIL if the compound is not yet in session memory.",
      },
      {
        step: 4,
        title: "Build Cited Evidence Synthesis",
        tools: [],
        stageTag: "Verify & Write",
        logic: "Weaves retrieved takeaways, toxicity warnings, and trial maturity into prose with auto-appended numbered References.",
      },
    ],
    outputSections: [
      "1. Executive Evidence Verdict & Novelty",
      "2. Synthesized Kidney Efficacy Literature",
      "3. Integrated Nephrotoxicity & Clinical Trials Review",
      "4. Translational Takeaway",
    ],
    examplePrompt:
      "Check Europe PMC literature, nephrotoxicity reports, and clinical trials for dexamethasone in diabetic kidney disease",
  },
  {
    id: "compound-compare",
    shortLabel: "Compare Drugs",
    name: "Head-to-Head Compound Comparison",
    color: "#0d9488",
    maxSteps: 5,
    whenUsed: "Comparing 2-4 drugs side-by-side (e.g., Compare dexamethasone and losartan, or Compare #1 and #2).",
    allowedTools: [
      "compare_compounds",
      "search_literature",
      "search_clinical_trials",
    ],
    workflow: [
      {
        step: 1,
        title: "Build Side-by-Side Matrix",
        tools: ["compare_compounds"],
        stageTag: "Compute",
        logic: "Aligns 2-4 compounds across clinical phase, MoA, T-DIKI v2, FDA DIRIL, PROGENy pathways, and 9 renal pathology modules.",
      },
      {
        step: 2,
        title: "Audit Top-2 Literature & Trials",
        tools: ["search_literature", "search_clinical_trials"],
        stageTag: "Evidence",
        logic: "Batches kidney efficacy, nephrotoxicity, and clinical trial checks for the top two compared drugs (reusing prior session results).",
      },
      {
        step: 3,
        title: "Contrast Module & Safety Trade-offs",
        tools: [],
        stageTag: "Auto-Reflect",
        logic: "Weighs anti-fibrotic activity (ECM_fibrosis, TGFb_SMAD) against podocyte/metabolic protection (Podocyte_slit, PT_FAO_mito) and risk.",
      },
      {
        step: 4,
        title: "Deliver Context Verdict",
        tools: [],
        stageTag: "Verify & Write",
        logic: "Verifies all numbers and citations, then states clearly which drug leads on kidney safety vs. anti-fibrotic efficacy.",
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
