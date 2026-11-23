"""End-to-end test for POST /api/v1/agent/run against a live server."""
import json
import os
import urllib.request

BASE = os.environ.get("NEPHRO_API_URL", "http://127.0.0.1:8099").rstrip("/")

AGENT_EXAMPLES = [
    ("SOP-6", "Find reversal drugs for the DKD glomeruli case"),
    (
        "SOP-1",
        "Up: COL1A1 COL3A1 FN1 TGFB1 SERPINE1 LCN2 HAVCR1; Down: NPHS1 NPHS2 PODXL PPARA PPARGC1A CPT1A. Approved drugs only, low nephrotoxicity risk",
    ),
    ("SOP-3", "Inhibit SMAD3 and TGFb, activate PPARA"),
    ("SOP-6", "Run the LN glomeruli case"),
    ("SOP-2", "Profile dexamethasone"),
    ("SOP-2", "Is tacrolimus nephrotoxic? Show its kidney safety profile"),
    ("SOP-4", "Which compounds mimic knockdown of TGFBR1?"),
    ("SOP-5", "Find compounds structurally similar to CC(=O)OC1=CC=CC=C1C(=O)O"),
]


def post_agent(text: str, use_llm: bool = False) -> dict:
    req = urllib.request.Request(
        f"{BASE}/api/v1/agent/run",
        data=json.dumps({"text": text, "use_llm": use_llm}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        assert resp.status == 200
        return json.loads(resp.read())


def main():
    for expected_sop, prompt in AGENT_EXAMPLES:
        out = post_agent(prompt)
        assert out["status"] == "ok", (prompt, out)
        assert out["sop_id"] == expected_sop, (prompt, out["sop_id"])
        assert len(out["table"]["rows"]) > 0, (prompt, out["table"])
        if expected_sop == "SOP-2":
            assert len(out["facts"]) >= 6, out["facts"]
        tool_steps = [s for s in out["steps"] if str(s.get("tool", "")).startswith("nephro_")]
        assert len(tool_steps) >= 1 and tool_steps[0]["status"] == "done", out["steps"]
        print(f"  [OK] {expected_sop} rows={len(out['table']['rows'])} ms={out['elapsed_ms']} | {prompt[:55]}")

    dex = post_agent("Profile dexamethasone")
    assert dex["resolved"].get("pert_id", "").startswith("BRD-"), dex["resolved"]

    fsgs = post_agent("Run the FSGS case")
    assert fsgs["status"] == "needs_input", fsgs

    oos = post_agent("What is the capital of France?")
    assert oos["status"] == "out_of_scope", oos

    print("test_agent_run_e2e OK")


if __name__ == "__main__":
    main()
