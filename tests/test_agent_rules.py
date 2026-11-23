"""Pure unit tests for deterministic SOP router rules (no store required)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agent import route  # noqa: E402


def main():
    r = route("Find reversal drugs for the DKD glomeruli case", use_llm=False)
    assert r["sop_id"] == "SOP-6" and r["params"]["case_id"] == "DKD", r

    r = route("Inhibit SMAD3 and activate PPARA", use_llm=False)
    assert r["sop_id"] == "SOP-3" and r["params"]["targets"] == {"SMAD3": -1, "PPARA": 1}, r

    r = route("Inhibit SMAD3 and TGFb, activate PPARA", use_llm=False)
    assert r["sop_id"] == "SOP-3" and r["params"]["targets"] == {
        "SMAD3": -1,
        "TGFb": -1,
        "PPARA": 1,
    }, r

    r = route("Compounds that inhibit TGFB signaling", use_llm=False)
    assert r["sop_id"] == "SOP-3" and r["params"]["targets"] == {"TGFB": -1}, r

    r = route("寻找抑制 SMAD3 通路的化合物", use_llm=False)
    assert r["sop_id"] == "SOP-3" and r["params"]["targets"] == {"SMAD3": -1}, r

    smi = "CC(=O)OC1=CC=CC=C1C(=O)O"
    r = route(f"Find compounds structurally similar to {smi}", use_llm=False)
    assert r["sop_id"] == "SOP-5" and r["params"]["smiles"] == smi, r

    r = route("Find analogs of dexamethasone", use_llm=False)
    assert r["sop_id"] == "SOP-5", r

    r = route("Which compounds mimic knockdown of TGFBR1?", use_llm=False)
    assert r["sop_id"] == "SOP-4" and r["params"]["gene"] == "TGFBR1", r

    ex2 = (
        "Up: COL1A1 COL3A1 FN1 TGFB1 SERPINE1 LCN2 HAVCR1; "
        "Down: NPHS1 NPHS2 PODXL PPARA PPARGC1A CPT1A. "
        "Approved drugs only, low nephrotoxicity risk"
    )
    r = route(ex2, use_llm=False)
    assert r["sop_id"] == "SOP-1", r
    assert len(r["params"]["up_genes"]) == 7 and len(r["params"]["down_genes"]) == 6, r
    assert r["params"]["filters"].get("approved_only") is True, r
    assert r["params"]["filters"].get("max_diki_tier") == "Low", r

    r = route("What is the weather today?", use_llm=False)
    assert r["sop_id"] == "OUT_OF_SCOPE", r

    r = route("I am taking notes", use_llm=False)
    assert r["sop_id"] != "SOP-6", r

    print("test_agent_rules OK")


if __name__ == "__main__":
    main()
