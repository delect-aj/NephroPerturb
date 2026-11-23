"""Strict citation, compound-ID, and numeric grounding verifier (v2)."""
from dataclasses import dataclass, field
import re

PMID_CITE_RE = re.compile(
    r"(?:PMID[:\s#-]*|europepmc\.org/article/MED/|pubmed\.ncbi\.nlm\.nih\.gov/)(\d{5,9})\b",
    re.I,
)
BRACKET_NUM_CITE_RE = re.compile(r"\[(?:PMID[:\s]*)?(\d{6,9})\]", re.I)
NCT_RE = re.compile(r"\b(NCT\d{8})\b", re.I)
BRD_RE = re.compile(r"\b(BRD-[A-Z0-9]{4,})\b", re.I)
NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_.\-/])(-?\d+(?:\.\d+)?)(%?)")

# Patterns whose trailing numbers should not trigger numeric-hallucination failures
_NOISE_SPAN_RE = re.compile(
    r"(?:PMID[:\s#-]*\d{5,9}|NCT\d{8}|BRD-[A-Z0-9-]+|GSE\d+|SOP-\d|"
    r"T-?DIKI\s*v?\d+|ECFP\d*|Phase\s*[0-4]|Level-?\d|K-?PRL|v\d+\.\d+(?:\.\d+)?|"
    r"https?://\S+|#\d{1,2}\b)",
    re.I,
)


@dataclass
class EvidencePool:
    pmids: set[str] = field(default_factory=set)
    ncts: set[str] = field(default_factory=set)
    pert_ids: set[str] = field(default_factory=set)
    compound_names: set[str] = field(default_factory=set)
    numbers: list[float] = field(default_factory=list)
    text_blobs: list[str] = field(default_factory=list)
    _seen_text_numbers: set[str] | None = None

    def ingest(self, obj) -> None:
        self._seen_text_numbers = None
        if obj is None or isinstance(obj, bool):
            return
        if isinstance(obj, (int, float)):
            if abs(float(obj)) < 1e12:
                self.numbers.append(float(obj))
            return
        if isinstance(obj, str):
            s = obj.strip()
            if s:
                self.text_blobs.append(s)
                for m in BRD_RE.findall(s):
                    self.pert_ids.add(m.upper())
                for m in NCT_RE.findall(s):
                    self.ncts.add(m.upper())
            return
        if isinstance(obj, dict):
            if obj.get("pmid"):
                self.pmids.add(str(obj["pmid"]).strip())
            if obj.get("nct_id"):
                self.ncts.add(str(obj["nct_id"]).strip().upper())
            if obj.get("pert_id"):
                self.pert_ids.add(str(obj["pert_id"]).strip().upper())
            if obj.get("pert_iname"):
                self.compound_names.add(str(obj["pert_iname"]).strip().lower())
            for pm in obj.get("pmids") or []:
                self.pmids.add(str(pm).strip())
            for nct in obj.get("ncts") or []:
                self.ncts.add(str(nct).strip().upper())
            for v in obj.values():
                self.ingest(v)
            return
        if isinstance(obj, (list, tuple)):
            for v in obj:
                self.ingest(v)

    def number_in_text_blobs(self, raw_num: str) -> bool:
        if self._seen_text_numbers is None:
            found = set()
            for blob in self.text_blobs:
                for raw, _pct in NUMBER_RE.findall(blob):
                    found.add(raw)
            self._seen_text_numbers = found
        return raw_num in self._seen_text_numbers


def verify_grounded_response(text: str, pool: EvidencePool) -> dict:
    """Audit LLM synthesis strictly against tool & session evidence pool."""
    body = text or ""
    hard_violations: list[str] = []
    soft_warnings: list[str] = []

    pmids_cited = list(
        dict.fromkeys(PMID_CITE_RE.findall(body) + BRACKET_NUM_CITE_RE.findall(body))
    )
    bad_pmids = [p for p in pmids_cited if p not in pool.pmids]
    if bad_pmids:
        hard_violations.append(f"Unverified PMID(s): {', '.join(bad_pmids[:5])}")

    ncts_cited = list(dict.fromkeys(m.upper() for m in NCT_RE.findall(body)))
    bad_ncts = [n for n in ncts_cited if n not in pool.ncts]
    if bad_ncts:
        hard_violations.append(f"Unverified NCT ID(s): {', '.join(bad_ncts[:5])}")

    brds_cited = list(dict.fromkeys(m.upper() for m in BRD_RE.findall(body)))
    bad_brds = [b for b in brds_cited if b not in pool.pert_ids]
    if bad_brds:
        hard_violations.append(f"Unverified BRD ID(s): {', '.join(bad_brds[:5])}")

    # Check quantitative claims (strip known identifier tokens first)
    cleaned_for_nums = _NOISE_SPAN_RE.sub(" ", body)
    unmatched_nums: list[str] = []
    for raw, pct in NUMBER_RE.findall(cleaned_for_nums):
        try:
            val = float(raw)
        except ValueError:
            continue
        is_int = "." not in raw and val == int(val)
        if not pct and is_int and (abs(val) <= 20 or 1950 <= val <= 2035):
            continue
        if is_int and str(int(abs(val))) in pool.pmids:
            continue
        if pool.number_in_text_blobs(raw):
            continue
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        tol = max(0.06, 0.55 * (10 ** (-decimals)))
        matched = any(
            abs(val - v) <= tol or (val > 0 and v < 0 and abs(val - abs(v)) <= tol)
            for v in pool.numbers
        )
        if not matched and pct:
            matched = any(
                abs(val / 100.0 - v) <= max(0.015, tol / 100.0)
                or (val > 0 and v < 0 and abs(val / 100.0 - abs(v)) <= max(0.015, tol / 100.0))
                for v in pool.numbers
            )
        if not matched:
            unmatched_nums.append(f"{raw}{pct}")

    # Require >= 2 unmatched floats/numbers (or any invented negative/score float) to fail hard
    unmatched_floats = [n for n in unmatched_nums if "." in n or "%" in n]
    if len(unmatched_floats) >= 2 or len(unmatched_nums) >= 3:
        hard_violations.append(f"Ungrounded number(s): {', '.join(unmatched_nums[:5])}")
    elif unmatched_nums:
        soft_warnings.append(f"Minor unverified prose number(s): {', '.join(unmatched_nums[:3])}")

    verified = len(hard_violations) == 0
    return {
        "verified": verified,
        "mode": "grounded_llm" if verified else "unverified",
        "hard_violations": hard_violations,
        "soft_warnings": soft_warnings,
        "pmids_cited": [p for p in pmids_cited if p in pool.pmids],
        "ncts_cited": [n for n in ncts_cited if n in pool.ncts],
        "brds_cited": [b for b in brds_cited if b in pool.pert_ids],
    }


def build_repair_prompt(draft: str, violations: list[str], pool: EvidencePool) -> str:
    allowed_pmids = ", ".join(sorted(pool.pmids)[:12]) or "NONE"
    allowed_ncts = ", ".join(sorted(pool.ncts)[:10]) or "NONE"
    allowed_brds = ", ".join(sorted(pool.pert_ids)[:12]) or "NONE"
    return (
        "Your draft failed citation/numeric verification with these exact errors:\n"
        + "\n".join(f"- {v}" for v in violations)
        + "\n\nRewrite the response cleanly, removing or fixing every unverified item. "
        f"ONLY allowed PMIDs: [{allowed_pmids}]. ONLY allowed NCTs: [{allowed_ncts}]. "
        f"ONLY allowed BRD IDs: [{allowed_brds}]. "
        "Keep every score and fact 100% faithful to tool outputs.\n\nDraft:\n"
        + draft[:2500]
    )
