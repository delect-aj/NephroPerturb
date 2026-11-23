"""End-to-end test for v1.2.0 SSE streaming, multi-turn memory, compare & literature APIs."""
import json
import os
import time
import urllib.request
import uuid

BASE = os.environ.get("NEPHRO_API_URL", "http://127.0.0.1:8099").rstrip("/")


def get_json(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=20) as resp:
        assert resp.status == 200, (path, resp.status)
        return json.loads(resp.read())


def post_json(path: str, body: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        assert resp.status == 200, (path, resp.status)
        return json.loads(resp.read())


def stream_sse(body: dict, timeout: int = 60) -> tuple[list[tuple[str, dict]], dict]:
    req = urllib.request.Request(
        f"{BASE}/api/v1/agent/stream",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    events = []
    done_payload = {}
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        assert resp.status == 200
        assert "text/event-stream" in resp.headers.get("Content-Type", "")
        assert "gzip" not in resp.headers.get("Content-Encoding", "").lower(), resp.headers
        cur_event = "message"
        cur_data = []
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            if not line:
                if cur_data:
                    payload = json.loads("\n".join(cur_data))
                    events.append((cur_event, payload))
                    if cur_event == "done":
                        done_payload = payload
                    cur_event = "message"
                    cur_data = []
                continue
            if line.startswith(":"):
                continue
            if line.startswith("event:"):
                cur_event = line[6:].strip()
            elif line.startswith("data:"):
                cur_data.append(line[5:].strip())
    return events, done_payload


def main():
    h = get_json("/health")
    assert h["version"] == "1.2.1" and h["agent_version"] == "1.2.1", h

    sk = get_json("/api/v1/agent/skills")
    assert len(sk["skills"]) == 6, sk

    st = get_json("/api/v1/agent/status")
    assert st["version"] == "1.2.1" and "quota" in st, st

    # 1. Direct Literature + ClinicalTrials search & cache latency check
    t0 = time.perf_counter()
    lit1 = post_json("/api/v1/literature/search", {"entity": "dexamethasone", "disease_context": "DKD"})
    t_cold = time.perf_counter() - t0
    assert lit1["literature"]["papers"] or lit1["literature"]["provider"] != "unavailable", lit1
    assert lit1["literature"].get("synthesis") is not None, lit1["literature"]
    if lit1["literature"]["papers"]:
        assert lit1["literature"]["papers"][0].get("takeaway"), lit1["literature"]["papers"][0]
    assert lit1["clinical_trials"] is not None
    t0 = time.perf_counter()
    lit2 = post_json("/api/v1/literature/search", {"entity": "dexamethasone", "disease_context": "DKD"})
    t_warm = time.perf_counter() - t0
    assert lit2["literature"]["cached"] is True and t_warm < 0.25, (t_cold, t_warm)
    print(f"  [OK] literature search + synthesis + 7d cache ({t_cold:.2f}s -> {t_warm*1000:.1f}ms, provider={lit1['literature']['provider']})")

    # 2. Direct head-to-head comparison
    cmp_res = post_json("/api/v1/compounds/compare", {"tokens": ["dexamethasone", "losartan"]})
    assert len(cmp_res["compounds"]) == 2 and "safest_kidney" in cmp_res["highlights"], cmp_res
    print(f"  [OK] compound compare ({cmp_res['highlights']})")

    # 3. Multi-turn SSE stream (Turn 1: DKD cohort repurposing + literature)
    sid = f"e2e-{uuid.uuid4().hex[:10]}"
    ev1, done1 = stream_sse({
        "text": "Find reversal drugs for the DKD glomeruli case and verify literature",
        "session_id": sid,
        "mode": "fast",
        "include_literature": True,
    })
    ev_names = [e[0] for e in ev1]
    assert "session" in ev_names and "skill_selected" in ev_names and "tool_result" in ev_names and "done" in ev_names, ev_names
    assert done1["status"] == "ok" and done1["skill_id"] == "disease-repurposing", done1
    assert done1["verification"]["verified"] is True, done1["verification"]
    assert len(done1["table"]["rows"]) > 0, done1
    assert "### 3. Literature & Clinical Synthesis" in done1["summary"], done1["summary"]
    assert all("synthesis" in g for g in done1["literature"]), done1["literature"]
    print(f"  [OK] SSE Turn 1 (disease-repurposing, rows={len(done1['table']['rows'])}, lits={len(done1['literature'])}, pmids={done1['verification']['pmids_cited']})")

    # 4. Multi-turn SSE stream (Turn 2: follow-up ordinal reference "#1 and #2")
    ev2, done2 = stream_sse({
        "text": "Compare #1 and #2 head-to-head",
        "session_id": sid,
        "mode": "fast",
        "include_literature": True,
    })
    assert done2["status"] == "ok" and done2["skill_id"] == "compound-compare", done2
    assert done2.get("comparison") and len(done2["comparison"]["compounds"]) == 2, done2
    assert done2["verification"]["verified"] is True
    assert "### 3. Literature & Clinical Synthesis" in done2["summary"], done2["summary"]
    print(f"  [OK] SSE Turn 2 multi-turn compare (#1 vs #2 -> {done2['comparison']['highlights']})")

    # 5. Toxicity rescue flow
    _, done_tox = stream_sse({
        "text": "Is tacrolimus nephrotoxic and are there safer Low-DIKI analogs?",
        "session_id": sid,
        "mode": "fast",
        "include_literature": True,
    })
    assert done_tox["status"] == "ok" and done_tox["skill_id"] == "toxicity-rescue", done_tox
    assert len(done_tox["table"]["rows"]) > 0, done_tox
    assert "### 3. Literature & Clinical Synthesis" in done_tox["summary"], done_tox["summary"]
    print(f"  [OK] SSE toxicity-rescue (analogs={len(done_tox['table']['rows'])})")

    # 6. Optional live DeepSeek ReAct verification (fixed sections + cited PMIDs + no truncation)
    if st["llm_configured"] and st["quota"]["allowed"]:
        _, done_llm = stream_sse({
            "text": "Find reversal drugs for the DKD glomeruli case, auto-filter High T-DIKI hits if needed, and verify literature & clinical trials for top candidates",
            "session_id": f"e2e-llm-{uuid.uuid4().hex[:8]}",
            "mode": "auto",
            "include_literature": True,
        }, timeout=90)
        assert done_llm["status"] == "ok", done_llm
        assert done_llm["mode_effective"] == "deepseek_react", done_llm
        assert done_llm["verification"]["verified"] is True, done_llm["verification"]
        assert "Literature & Clinical Synthesis" in done_llm["summary"], done_llm["summary"]
        assert len(done_llm["verification"].get("pmids_cited") or []) >= 1, done_llm["summary"]
        assert 0 < done_llm["usage"]["total_tokens"] < 15000, done_llm["usage"]
        print(
            f"  [OK] DeepSeek live ReAct (tokens={done_llm['usage']['total_tokens']}, "
            f"pmids={done_llm['verification']['pmids_cited']}, ms={done_llm['elapsed_ms']})"
        )
    else:
        print("  [SKIP] DeepSeek live ReAct (key not configured or quota depleted)")

    print("test_react_stream_e2e OK")


if __name__ == "__main__":
    main()
