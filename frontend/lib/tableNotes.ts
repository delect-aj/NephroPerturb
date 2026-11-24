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
  { match: /^pert_id$|^broad\s*id$/i, term: "pert_id", desc: "LINCS compound ID" },
  { match: /^phase$|clinical\s*phase/i, term: "Phase", desc: "clinical stage" },
  { match: /^rtps$/i, term: "RTPS", desc: "renal priority score (higher = better)" },
  { match: /^renalconn$/i, term: "RenalConn", desc: "kidney reversal score (more negative = stronger)" },
  { match: /pathway\/tf\s*score/i, term: "Pathway/TF Score", desc: "target direction alignment (higher = better)" },
  { match: /^wtcs$/i, term: "WTCS", desc: "weighted connectivity score (more negative = stronger reversal)" },
  { match: /^score$|reversal/i, term: "Score", desc: "reversal priority score" },
  { match: /t-?diki/i, term: "T-DIKI", desc: "predicted kidney risk (Low/Mod/High)" },
  { match: /diril/i, term: "DIRIL", desc: "FDA renal injury label" },
  { match: /^moa$/i, term: "MoA", desc: "mechanism of action" },
  { match: /tanimoto/i, term: "Tanimoto", desc: "ECFP4 2D similarity (0–1)" },
  { match: /cosine/i, term: "Cosine", desc: "transcriptional mimicry (-1 to 1)" },
  { match: /k-?prl/i, term: "K-PRL", desc: "kidney perturbation profile" },
  { match: /^z-?score$/i, term: "Z-score", desc: "expression shift (+ up, - down)" },
  { match: /ecm_?fibrosis/i, term: "ECM_fibrosis", desc: "fibrosis activity (lower = anti-fibrotic)" },
  { match: /podocyte_?slit/i, term: "Podocyte_slit", desc: "podocyte integrity (higher = protective)" },
  { match: /pt_?fao/i, term: "PT_FAO_mito", desc: "tubular mitochondrial FAO (higher = protective)" },
  { match: /tgfb_?smad/i, term: "TGFb_SMAD", desc: "TGF-beta/SMAD signaling (lower = better)" },
];

export const COMPARE_TABLE_NOTES: TableHeaderNote[] = [
  { term: "T-DIKI", desc: "predicted kidney risk (prob)" },
  { term: "DIRIL", desc: "FDA renal injury label" },
  { term: "Modules", desc: "lower fibrosis/TGFb/NFkB/KIM1 & higher podocyte/FAO are favorable" },
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
