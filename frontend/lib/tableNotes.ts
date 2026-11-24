export interface TableHeaderNote {
  term: string;
  desc: string;
}

interface MatcherRule {
  match: RegExp;
  term: string;
  desc: string;
}

const HEADER_RULES: MatcherRule[] = [
  { match: /^pert_id$|^broad\s*id$/i, term: "pert_id", desc: "LINCS compound identifier" },
  { match: /^phase$|clinical\s*phase/i, term: "Phase", desc: "clinical development stage" },
  { match: /^rtps$/i, term: "RTPS", desc: "Renal Therapeutic Priority Score (higher indicates stronger reversal and safety)" },
  { match: /^renalconn$/i, term: "RenalConn", desc: "kidney-weighted connectivity score (more negative indicates stronger reversal)" },
  { match: /pathway\/tf\s*score/i, term: "Pathway/TF Score", desc: "directional alignment across target pathways/TFs (higher is better)" },
  { match: /^wtcs$/i, term: "WTCS", desc: "Weighted Connectivity Score (more negative indicates stronger reversal)" },
  { match: /^score$|reversal/i, term: "Score", desc: "composite reversal priority score" },
  { match: /t-?diki/i, term: "T-DIKI", desc: "predicted nephrotoxicity risk tier (Low / Moderate / High)" },
  { match: /diril/i, term: "DIRIL", desc: "FDA Drug-Induced Renal Injury List classification" },
  { match: /^moa$/i, term: "MoA", desc: "mechanism of action" },
  { match: /tanimoto/i, term: "Tanimoto", desc: "2D structural similarity coefficient (ECFP4, 0–1)" },
  { match: /cosine/i, term: "Cosine", desc: "transcriptional knockdown similarity (−1 to 1)" },
  { match: /k-?prl/i, term: "K-PRL", desc: "kidney-context perturbation gene signature" },
  { match: /^z-?score$/i, term: "Z-score", desc: "differential expression magnitude (+ up-regulated, − down-regulated)" },
  { match: /ecm_?fibrosis/i, term: "ECM_fibrosis", desc: "fibrosis module activity (lower indicates anti-fibrotic effect)" },
  { match: /podocyte_?slit/i, term: "Podocyte_slit", desc: "podocyte integrity score (higher indicates protective effect)" },
  { match: /pt_?fao/i, term: "PT_FAO_mito", desc: "tubular mitochondrial fatty-acid oxidation score (higher is protective)" },
  { match: /tgfb_?smad/i, term: "TGFb_SMAD", desc: "TGF-beta / SMAD profibrotic signaling score (lower is favorable)" },
];

export const COMPARE_TABLE_NOTES: TableHeaderNote[] = [
  { term: "T-DIKI", desc: "predicted nephrotoxicity risk tier and probability" },
  { term: "DIRIL", desc: "FDA renal injury reference classification" },
  { term: "Pathology Modules", desc: "lower fibrosis/injury scores and higher podocyte/metabolic scores are favorable" },
];

export function getTableHeaderNotes(headers: string[]): TableHeaderNote[] {
  const seen = new Set<string>();
  const out: TableHeaderNote[] = [];
  for (const raw of headers) {
    const clean = String(raw || "").replace(/[*`]/g, "").trim();
    if (!clean) continue;
    for (const rule of HEADER_RULES) {
      if (rule.match.test(clean) && !seen.has(rule.term)) {
        seen.add(rule.term);
        out.push({ term: rule.term, desc: rule.desc });
        break;
      }
    }
  }
  return out;
}
