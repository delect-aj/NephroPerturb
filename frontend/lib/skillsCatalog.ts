export interface SkillStepDoc {
  step: number;
  title: string;
  tools: string[];
  stageTag?: "Scoring & Analysis" | "Safety Filtering" | "Literature & Trials" | "Synthesis & Verification";
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
    title: "Reproducible Execution",
    detail: "Fixed decoding parameters and workflow-specific tool boundaries ensure consistent, repeatable analysis across runs.",
  },
  {
    title: "Dual Efficacy & Safety Literature",
    detail: "Searches Europe PMC and PubMed for both therapeutic evidence and drug-induced kidney injury alongside ClinicalTrials.gov records.",
  },
  {
    title: "Automated Fact & Citation Audit",
    detail: "Every reported score, compound ID, PubMed ID (PMID), and trial identifier (NCT) is verified against retrieved source data.",
  },
  {
    title: "Traceable Bibliography",
    detail: "Numbered references and metric definitions are compiled directly from verified database and publication records.",
  },
];

export const SKILLS_CATALOG: SkillLogicDoc[] = [
  {
    id: "disease-repurposing",
    shortLabel: "Disease Repurposing",
    name: "Disease-to-Evidence Repurposing",
    color: "#2563eb",
    maxSteps: 6,
    whenUsed: "Screening 10 human kidney biopsy cohorts (DKD, LN, IgAN, CKD, AKI), custom Up/Down gene signatures, or pathway/TF combinations.",
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
        title: "Rank Candidate Compounds",
        tools: ["run_cohort_case", "score_gene_signature", "query_pathway_tf"],
        stageTag: "Scoring & Analysis",
        logic: "Evaluates 21,299 compounds for disease-signature reversal and checks whether any top-ranked candidates carry high predicted nephrotoxicity.",
      },
      {
        step: 2,
        title: "Filter Out High-Risk Hits",
        tools: ["find_safe_analogs"],
        stageTag: "Safety Filtering",
        logic: "If top candidates show high predicted nephrotoxicity (T-DIKI) or positive FDA DIRIL status, automatically re-screens for safer approved compounds or structural analogs.",
      },
      {
        step: 3,
        title: "Profile Lead Candidate",
        tools: ["profile_compound"],
        stageTag: "Scoring & Analysis",
        logic: "Retrieves the top safe candidate's molecular targets, mechanism of action, signaling pathway activity, renal pathology modules, and kidney gene signature.",
      },
      {
        step: 4,
        title: "Synthesize Literature & Clinical Trials",
        tools: ["search_literature", "search_clinical_trials"],
        stageTag: "Literature & Trials",
        logic: "Queries Europe PMC / PubMed and ClinicalTrials.gov for therapeutic and renal safety studies on the leading candidates, then compiles a cited report.",
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
    shortLabel: "Safety & Analog Rescue",
    name: "Compound Safety & Toxicity Rescue",
    color: "#dc2626",
    maxSteps: 5,
    whenUsed: "Evaluating a compound's nephrotoxicity risk, understanding structural and transcriptional toxicity drivers, or identifying safer structural analogs.",
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
        title: "Evaluate Nephrotoxicity & Risk Drivers",
        tools: ["profile_compound", "explain_tdiki"],
        stageTag: "Scoring & Analysis",
        logic: "Computes predicted nephrotoxicity risk (T-DIKI v2), checks FDA DIRIL classification, and identifies the chemical and transcriptional features driving toxicity.",
      },
      {
        step: 2,
        title: "Identify Safer Structural Analogs",
        tools: ["find_safe_analogs"],
        stageTag: "Safety Filtering",
        logic: "When nephrotoxicity risk is Moderate or High (or safer alternatives are requested), searches structural neighbors (ECFP4) to identify lower-risk analogs.",
      },
      {
        step: 3,
        title: "Retrieve Renal Safety Literature & Trials",
        tools: ["search_literature", "search_clinical_trials"],
        stageTag: "Literature & Trials",
        logic: "Collects peer-reviewed publications on drug-induced kidney injury alongside registered clinical trials involving the compound.",
      },
      {
        step: 4,
        title: "Formulate Risk Mitigation Strategy",
        tools: [],
        stageTag: "Synthesis & Verification",
        logic: "Integrates toxicity attribution, analog availability, and clinical evidence into practical recommendations for monitoring or scaffold substitution.",
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
    shortLabel: "Target & Mimicry",
    name: "Target-to-Lead & Genetic Mimicry",
    color: "#d97706",
    maxSteps: 5,
    whenUsed: "Investigating a disease target gene, its expression across nephron segments, and small molecules that mimic genetic knockdown.",
    allowedTools: [
      "profile_target",
      "profile_compound",
      "search_literature",
      "search_clinical_trials",
    ],
    workflow: [
      {
        step: 1,
        title: "Map Nephron Expression & Knockdown Mimics",
        tools: ["profile_target"],
        stageTag: "Scoring & Analysis",
        logic: "Examines target expression across kidney cell types, lists known direct drugs, and ranks compounds whose signatures mimic shRNA/CRISPR knockdown.",
      },
      {
        step: 2,
        title: "Assess Lead Compound Safety",
        tools: ["profile_compound"],
        stageTag: "Safety Filtering",
        logic: "Profiles the top knockdown-mimicking compound to evaluate its mechanism of action, renal pathway activity, and predicted nephrotoxicity risk.",
      },
      {
        step: 3,
        title: "Retrieve Target & Lead Literature",
        tools: ["search_literature", "search_clinical_trials"],
        stageTag: "Literature & Trials",
        logic: "Searches PubMed for studies on both the target gene and the lead mimicking compound, along with registered kidney clinical trials.",
      },
      {
        step: 4,
        title: "Prioritize Experimental Validation",
        tools: [],
        stageTag: "Synthesis & Verification",
        logic: "Combines target localization, transcriptional mimicry, safety metrics, and literature into a focused experimental validation plan.",
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
    shortLabel: "Structure & MoA",
    name: "Structure Similarity & MoA Validation",
    color: "#4f46e5",
    maxSteps: 4,
    whenUsed: "Querying a chemical structure (SMILES) or compound ID to find structural analogs, infer mechanism of action, and assess renal safety.",
    allowedTools: [
      "find_safe_analogs",
      "profile_compound",
      "search_literature",
    ],
    workflow: [
      {
        step: 1,
        title: "Search 2D Structural Neighbors",
        tools: ["find_safe_analogs"],
        stageTag: "Scoring & Analysis",
        logic: "Computes 2048-bit ECFP4 Tanimoto similarity across 21,299 compounds and infers the most likely mechanism of action from annotated neighbors.",
      },
      {
        step: 2,
        title: "Profile Closest Annotated Analog",
        tools: ["profile_compound"],
        stageTag: "Safety Filtering",
        logic: "Examines the nearest annotated analog for molecular targets, signaling pathways, renal pathology modules, and predicted nephrotoxicity risk.",
      },
      {
        step: 3,
        title: "Review Analog Kidney Literature",
        tools: ["search_literature"],
        stageTag: "Literature & Trials",
        logic: "Searches Europe PMC / PubMed for kidney efficacy and safety studies on the closest analog to contextualize the scaffold.",
      },
      {
        step: 4,
        title: "Summarize Pharmacology & Scaffold Advice",
        tools: [],
        stageTag: "Synthesis & Verification",
        logic: "Synthesizes structural similarity, inferred mechanism of action, renal safety, and published evidence to guide scaffold optimization.",
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
    whenUsed: "Conducting focused PubMed and ClinicalTrials.gov evidence reviews, assessing repurposing novelty, or following up on ranked candidates (#1, #2).",
    allowedTools: [
      "search_literature",
      "search_clinical_trials",
      "profile_compound",
    ],
    workflow: [
      {
        step: 1,
        title: "Resolve Compounds, Genes & Disease Context",
        tools: [],
        stageTag: "Scoring & Analysis",
        logic: "Identifies the queried compounds or genes (including #1 / #2 references from earlier turns) and retains the active kidney disease context.",
      },
      {
        step: 2,
        title: "Retrieve Efficacy & Nephrotoxicity Studies",
        tools: ["search_literature"],
        stageTag: "Literature & Trials",
        logic: "Performs separate Title/Abstract searches in Europe PMC and PubMed for therapeutic efficacy and renal toxicity, then classifies evidence maturity.",
      },
      {
        step: 3,
        title: "Check Clinical Trials & Safety Baseline",
        tools: ["search_clinical_trials", "profile_compound"],
        stageTag: "Literature & Trials",
        logic: "Retrieves registered kidney clinical trials from ClinicalTrials.gov and adds NephroSafe toxicity metrics when not already profiled.",
      },
      {
        step: 4,
        title: "Compile Cited Evidence Review",
        tools: [],
        stageTag: "Synthesis & Verification",
        logic: "Synthesizes study findings, renal safety signals, and clinical trial phases into a cohesive review with a numbered reference list.",
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
    shortLabel: "Drug Comparison",
    name: "Head-to-Head Compound Comparison",
    color: "#0d9488",
    maxSteps: 5,
    whenUsed: "Comparing two to four compounds side-by-side across renal efficacy modules, pathway activity, nephrotoxicity risk, and clinical evidence.",
    allowedTools: [
      "compare_compounds",
      "search_literature",
      "search_clinical_trials",
    ],
    workflow: [
      {
        step: 1,
        title: "Assemble Side-by-Side Comparison Matrix",
        tools: ["compare_compounds"],
        stageTag: "Scoring & Analysis",
        logic: "Aligns 2-4 compounds across clinical development phase, mechanism of action, predicted nephrotoxicity, PROGENy pathways, and 9 renal pathology modules.",
      },
      {
        step: 2,
        title: "Retrieve Comparative Literature & Trials",
        tools: ["search_literature", "search_clinical_trials"],
        stageTag: "Literature & Trials",
        logic: "Gathers peer-reviewed kidney efficacy and toxicity publications along with clinical trial records for the compared compounds.",
      },
      {
        step: 3,
        title: "Evaluate Efficacy vs. Safety Trade-offs",
        tools: [],
        stageTag: "Safety Filtering",
        logic: "Contrasts anti-fibrotic potency against podocyte and tubular metabolic preservation alongside predicted renal risk.",
      },
      {
        step: 4,
        title: "Provide Context-Specific Recommendation",
        tools: [],
        stageTag: "Synthesis & Verification",
        logic: "Summarizes which candidate is preferable for renal safety versus anti-fibrotic efficacy and recommends the best translational option.",
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
