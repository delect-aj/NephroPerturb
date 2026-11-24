export interface ResearchPlaybook {
  id: string;
  skillId: string;
  badge: string;
  title: string;
  subtitle: string;
  color: string;
  prompt: string;
}

export const RESEARCH_PLAYBOOKS: ResearchPlaybook[] = [
  {
    id: "pb-disease-evidence",
    skillId: "disease-repurposing",
    badge: "Disease -> Evidence",
    title: "DKD Reversal + Safety + Literature",
    subtitle: "Cohort screen -> auto filter Low T-DIKI -> top-2 PubMed & clinical trials",
    color: "#2563eb",
    prompt:
      "Find reversal drugs for the DKD glomeruli case, auto-filter High T-DIKI hits if needed, and verify literature & clinical trials for top candidates",
  },
  {
    id: "pb-tox-rescue",
    skillId: "toxicity-rescue",
    badge: "Safety & Rescue",
    title: "Tacrolimus Toxicity Rescue",
    subtitle: "T-DIKI attribution -> safer Low-DIKI analogs -> nephrotoxicity papers",
    color: "#dc2626",
    prompt:
      "Is tacrolimus nephrotoxic? Explain T-DIKI drivers, audit safety literature, and find safer Low-DIKI structural analogs",
  },
  {
    id: "pb-target-lead",
    skillId: "target-to-lead",
    badge: "Target -> Lead",
    title: "TGFBR1 Target-to-Lead Dossier",
    subtitle: "Nephron expression -> knockdown mimics -> lead safety & PubMed",
    color: "#d97706",
    prompt:
      "Analyze TGFBR1 in kidney disease: check nephron expression, top knockdown-mimicking drugs, lead safety, and literature evidence",
  },
  {
    id: "pb-compare",
    skillId: "compound-compare",
    badge: "Compare Drugs",
    title: "Dexamethasone vs. Losartan",
    subtitle: "Head-to-head renal fibrosis modules, podocyte scores & literature",
    color: "#0d9488",
    prompt:
      "Compare dexamethasone and losartan head-to-head on renal fibrosis modules, podocyte protection, T-DIKI safety, and kidney literature",
  },
];

export interface QuickExample {
  id: string;
  skillId: string | null;
  category: string;
  title: string;
  color: string;
  prompt: string;
}

export const QUICK_EXAMPLES: QuickExample[] = [
  {
    id: "qe-dkd",
    skillId: "disease-repurposing",
    category: "Disease Cohort",
    title: "DKD Reversal & Clinical Evidence",
    color: "#2563eb",
    prompt:
      "Find reversal drugs for the DKD glomeruli case, prioritize low-nephrotoxicity candidates, and summarize supporting literature and clinical trials",
  },
  {
    id: "qe-tox",
    skillId: "toxicity-rescue",
    category: "Drug Safety",
    title: "Tacrolimus Safety & Safer Analogs",
    color: "#dc2626",
    prompt:
      "Is tacrolimus nephrotoxic? Explain its T-DIKI risk drivers, review renal safety literature, and identify safer Low-DIKI structural analogs",
  },
  {
    id: "qe-target",
    skillId: "target-to-lead",
    category: "Target Biology",
    title: "TGFBR1 Knockdown Mimics",
    color: "#d97706",
    prompt:
      "Analyze TGFBR1 in kidney disease: examine nephron expression, top knockdown-mimicking drugs, lead safety, and published literature",
  },
  {
    id: "qe-compare",
    skillId: "compound-compare",
    category: "Drug Comparison",
    title: "Dexamethasone vs. Losartan",
    color: "#0d9488",
    prompt:
      "Compare dexamethasone and losartan head-to-head across renal fibrosis modules, podocyte protection, nephrotoxicity risk, and kidney literature",
  },
  {
    id: "qe-signature",
    skillId: "disease-repurposing",
    category: "Gene Signature",
    title: "Anti-Fibrotic Gene Signature",
    color: "#14b8a6",
    prompt:
      "Up: COL1A1 COL3A1 FN1 TGFB1 SERPINE1 LCN2 HAVCR1; Down: NPHS1 NPHS2 PODXL PPARA PPARGC1A CPT1A. Approved drugs only, low nephrotoxicity risk",
  },
  {
    id: "qe-pathway",
    skillId: null,
    category: "Pathway & TF",
    title: "Inhibit SMAD3/TGFb · Activate PPARA",
    color: "#7c3aed",
    prompt: "Inhibit SMAD3 and TGFb, activate PPARA",
  },
  {
    id: "qe-smiles",
    skillId: "structure-moa-evidence",
    category: "Chemical Structure",
    title: "Structure Similarity & MoA",
    color: "#4f46e5",
    prompt:
      "Find compounds structurally similar to CC(=O)OC1=CC=CC=C1C(=O)O, infer mechanism of action, and evaluate kidney safety",
  },
  {
    id: "qe-profile",
    skillId: "literature-evidence",
    category: "Literature Audit",
    title: "Dexamethasone Literature & Trials",
    color: "#059669",
    prompt:
      "Check Europe PMC literature, nephrotoxicity reports, and clinical trials for dexamethasone in diabetic kidney disease",
  },
];

export interface AgentExample {
  id: string;
  title: string;
  subtitle: string;
  sop: string;
  color: string;
  prompt: string;
}

export const AGENT_EXAMPLES: AgentExample[] = [
  {
    id: "fibrosis-safe",
    title: "Fibrosis Signature (Safe)",
    subtitle: "Approved drugs · Low T-DIKI filter",
    sop: "SOP-1",
    color: "#14b8a6",
    prompt:
      "Up: COL1A1 COL3A1 FN1 TGFB1 SERPINE1 LCN2 HAVCR1; Down: NPHS1 NPHS2 PODXL PPARA PPARGC1A CPT1A. Approved drugs only, low nephrotoxicity risk",
  },
  {
    id: "dex-profile",
    title: "Dexamethasone Profile",
    subtitle: "K-PRL signature, DIRIL & target expr",
    sop: "SOP-2",
    color: "#059669",
    prompt: "Profile dexamethasone",
  },
  {
    id: "tacrolimus-tox",
    title: "Tacrolimus Toxicity",
    subtitle: "T-DIKI v2 risk & DIRIL audit",
    sop: "SOP-2",
    color: "#dc2626",
    prompt: "Is tacrolimus nephrotoxic? Show its kidney safety profile",
  },
  {
    id: "pathway-smad-ppara",
    title: "SMAD3/TGFb − · PPARA +",
    subtitle: "Multi-target pathway & TF screen",
    sop: "SOP-3",
    color: "#7c3aed",
    prompt: "Inhibit SMAD3 and TGFb, activate PPARA",
  },
  {
    id: "tgfbr1-mimicry",
    title: "TGFBR1 Knockdown Mimic",
    subtitle: "Compounds matching shRNA/CRISPR",
    sop: "SOP-4",
    color: "#d97706",
    prompt: "Which compounds mimic knockdown of TGFBR1?",
  },
  {
    id: "aspirin-structure",
    title: "Aspirin Structure Match",
    subtitle: "ECFP4 Tanimoto scan from SMILES",
    sop: "SOP-5",
    color: "#4f46e5",
    prompt: "Find compounds structurally similar to CC(=O)OC1=CC=CC=C1C(=O)O",
  },
  {
    id: "dkd-cohort",
    title: "DKD Glomerular Cohort",
    subtitle: "GSE30528 reversal + NephroSafe flags",
    sop: "SOP-6",
    color: "#2563eb",
    prompt: "Find reversal drugs for the DKD glomeruli case",
  },
  {
    id: "ln-cohort",
    title: "LN Glomerular Cohort",
    subtitle: "Immune/epithelial context routing",
    sop: "SOP-6",
    color: "#0284c7",
    prompt: "Run the LN glomeruli case",
  },
];

export const SIGNATURE_PRESETS = [
  {
    id: "dkd-fibrosis",
    label: "DKD Fibrosis",
    context: "kprl",
    compartment: "whole_kidney",
    up: "COL1A1\nCOL3A1\nFN1\nTGFB1\nSERPINE1\nLCN2\nHAVCR1\nSPP1",
    down: "NPHS1\nNPHS2\nPODXL\nWT1\nPPARA\nPPARGC1A\nCPT1A",
  },
  {
    id: "ln-inflammation",
    label: "LN Inflammation",
    context: "renal_immune",
    compartment: "glomerulus",
    up: "STAT1\nIRF7\nCXCL10\nISG15\nMX1\nC3\nCCL2",
    down: "NPHS1\nNPHS2\nUMOD\nSLC34A1",
  },
  {
    id: "aki-injury",
    label: "AKI Tubular Injury",
    context: "renal_epi",
    compartment: "tubule",
    up: "HAVCR1\nLCN2\nSPP1\nSOX9\nKRT18\nVCAM1",
    down: "SLC34A1\nUMOD\nPPARGC1A\nCPT1A",
  },
  {
    id: "podocyte-loss",
    label: "Podocyte Injury",
    context: "kprl",
    compartment: "podocyte",
    up: "TGFB1\nSERPINE1\nCCN2\nFN1\nCOL4A1",
    down: "NPHS1\nNPHS2\nPODXL\nCD2AP\nSYNPO\nWT1",
  },
];

export const PATHWAY_PRESETS = [
  {
    id: "anti-fibrosis",
    label: "Inhibit SMAD3 + Activate PPARA",
    rows: [
      { name: "SMAD3", dir: -1 },
      { name: "PPARA", dir: 1 },
    ],
  },
  {
    id: "block-tgfb",
    label: "Inhibit TGFb + ECM_fibrosis",
    rows: [
      { name: "TGFb", dir: -1 },
      { name: "ECM_fibrosis", dir: -1 },
    ],
  },
  {
    id: "anti-inflamm",
    label: "Inhibit NFkB + STAT1",
    rows: [
      { name: "NFkB", dir: -1 },
      { name: "STAT1", dir: -1 },
    ],
  },
  {
    id: "tubular-rescue",
    label: "Restore PT_FAO_mito + Block Hypoxia",
    rows: [
      { name: "PT_FAO_mito", dir: 1 },
      { name: "Hypoxia", dir: -1 },
    ],
  },
];

export const COMPOUND_PRESETS = [
  "dexamethasone",
  "losartan",
  "empagliflozin",
  "metformin",
  "captopril",
  "tacrolimus",
];

export const STRUCTURE_PRESETS = [
  {
    label: "Aspirin (SMILES)",
    query: "CC(=O)OC1=CC=CC=C1C(=O)O",
  },
  {
    label: "Ibuprofen (SMILES)",
    query: "CC(C)Cc1ccc(cc1)C(C)C(=O)O",
  },
  {
    label: "Caffeine (SMILES)",
    query: "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
  },
  {
    label: "Dexamethasone (Name)",
    query: "dexamethasone",
  },
];
