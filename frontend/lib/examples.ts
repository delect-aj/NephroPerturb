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
    id: "dkd-cohort",
    title: "DKD Glomerular Cohort",
    subtitle: "GSE30528 reversal + NephroSafe flags",
    sop: "SOP-6",
    color: "#2563eb",
    prompt: "Find reversal drugs for the DKD glomeruli case",
  },
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
    id: "pathway-smad-ppara",
    title: "SMAD3/TGFb − · PPARA +",
    subtitle: "Multi-target pathway & TF screen",
    sop: "SOP-3",
    color: "#7c3aed",
    prompt: "Inhibit SMAD3 and TGFb, activate PPARA",
  },
  {
    id: "ln-cohort",
    title: "LN Glomerular Cohort",
    subtitle: "Immune/epithelial context routing",
    sop: "SOP-6",
    color: "#0284c7",
    prompt: "Run the LN glomeruli case",
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
