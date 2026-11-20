#!/usr/bin/env python
"""BM-4 (v2): 100-query SOP routing, slot F1, latency/throughput, and the
numeric/entity zero-hallucination verifier.

Mode A (0-LLM rules) always runs. Mode B (DeepSeek) runs only when
DEEPSEEK_API_KEY is configured; its absence is recorded, not faked.
"""
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))

QUERIES = ROOT / "benchmarks" / "bm4_queries_100.json"
OUT = ROOT / "benchmarks" / "outputs" / "bm4_latency_agent.json"
SLOT_KEYS = ("case_id", "gene", "targets", "smiles")


def pct(values, p):
    if not values:
        return None
    k = max(0, min(len(values) - 1, int(round((p / 100) * (len(values) - 1)))))
    return sorted(values)[k]


def slot_stats(queries, routed):
    tp = fp = fn = 0
    detail = []
    for q, r in zip(queries, routed):
        exp = q.get("expected_slots") or {}
        got = r.get("params", {}) or {}
        for key, expected in exp.items():
            if expected is True:  # presence-style slot (gene lists)
                hit = bool(got.get(key))
                tp += int(hit)
                fn += int(not hit)
        for key in SLOT_KEYS:
            if key in exp and isinstance(exp[key], str):
                got_val = got.get(key)
                hit = str(got_val).lower() == exp[key].lower() if got_val else False
                tp += int(hit)
                fn += int(not hit)
                if got_val and not hit:
                    fp += 1
        detail.append(r.get("params", {}))
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(f1, 4), "tp": tp, "fp": fp, "fn": fn}


def run_rules(queries):
    from app.agent import route
    routed, times = [], []
    for q in queries:
        t0 = time.perf_counter()
        routed.append(route(q["text"], use_llm=False))
        times.append((time.perf_counter() - t0) * 1000)
    acc = sum(1 for q, r in zip(queries, routed)
              if r.get("sop_id") == q["expected_sop"]) / len(queries)
    return {"accuracy": round(acc, 4), "slot_f1": slot_stats(queries, routed),
            "latency_ms": {"p50": round(statistics.median(times), 2),
                           "p95": round(pct(times, 95), 2)}, "routed": routed}


def run_llm(queries):
    import os
    if not os.environ.get("DEEPSEEK_API_KEY"):
        return {"status": "not_run_no_api_key"}
    from app.agent import route
    routed = [route(q["text"], use_llm=True) for q in queries]
    acc = sum(1 for q, r in zip(queries, routed)
              if r.get("sop_id") == q["expected_sop"]) / len(queries)
    return {"status": "run", "accuracy": round(acc, 4),
            "slot_f1": slot_stats(queries, routed)}


def engine_latency():
    from app.engine.scoring import rank_all, score_pathway_tf
    from app.core.store import get_store
    store = get_store()
    up = ["COL1A1", "COL3A1", "FN1", "TGFB1", "SERPINE1"]
    down = ["NPHS1", "NPHS2", "PPARGC1A", "CPT1A", "ACADM"]
    times_sig, times_pw, times_cmp = [], [], []
    for _ in range(12):
        t0 = time.perf_counter()
        rank_all(up, down, context="kprl")
        times_sig.append((time.perf_counter() - t0) * 1000)
    for _ in range(12):
        t0 = time.perf_counter()
        score_pathway_tf({"SMAD3": -1, "TGFB": -1})
        times_pw.append((time.perf_counter() - t0) * 1000)
    for _ in range(20):
        t0 = time.perf_counter()
        store.find_compound("dexamethasone")
        times_cmp.append((time.perf_counter() - t0) * 1000)
    return {"signature": {"p50": round(statistics.median(times_sig), 1),
                          "p95": round(pct(times_sig, 95), 1)},
            "pathway": {"p50": round(statistics.median(times_pw), 1),
                        "p95": round(pct(times_pw, 95), 1)},
            "compound": {"p50": round(statistics.median(times_cmp), 1),
                         "p95": round(pct(times_cmp, 95), 1)}}


def http_latency():
    import urllib.request
    base = "http://127.0.0.1:8091"
    payload = json.dumps({
        "up_genes": ["COL1A1", "COL3A1", "FN1", "TGFB1"],
        "down_genes": ["NPHS1", "NPHS2", "PPARA"], "top_k": 20}).encode()
    times = []
    for _ in range(10):
        t0 = time.perf_counter()
        req = urllib.request.Request(f"{base}/api/v1/query/signature", data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            json.loads(resp.read())
        times.append((time.perf_counter() - t0) * 1000)
    return {"signature_http_p50": round(statistics.median(times), 1),
            "signature_http_p95": round(pct(times, 95), 1)}


def concurrency_test():
    import urllib.request
    base = "http://127.0.0.1:8091"
    payload = json.dumps({
        "up_genes": ["COL1A1", "COL3A1", "FN1"],
        "down_genes": ["NPHS1", "PPARA"], "top_k": 10}).encode()

    def one(_):
        t0 = time.perf_counter()
        req = urllib.request.Request(f"{base}/api/v1/query/signature", data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            resp.read()
        return (time.perf_counter() - t0) * 1000

    results = []
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(one, range(96)))
    wall = time.perf_counter() - t0
    return {"requests": len(results), "workers": 16,
            "wall_s": round(wall, 2), "throughput_rps": round(len(results) / wall, 2),
            "p50_ms": round(statistics.median(results), 1),
            "p95_ms": round(pct(results, 95), 1)}


def hallucination_checks():
    from app.agent import summarize, verify_summary
    mock = {"results": [
        {"pert_id": "BRD-K11433652", "pert_iname": "aspirin", "rtps": 12.34,
         "renalconn": 10.2, "tdiki_tier": "Low", "diril_label": 0},
        {"pert_id": "BRD-K81418486", "pert_iname": "vorinostat", "rtps": 9.87,
         "renalconn": 8.4, "tdiki_tier": "Moderate", "diril_label": 0}]}
    honest = ("阿司匹林（BRD-K11433652）RTPS 为 12.34，RenalConn 10.2；"
              "伏立诺他（BRD-K81418486）RTPS 为 9.87。")
    fake_drug = "候选药物 ABC-9999 的 RTPS 为 21.5。"
    fake_number = "阿司匹林 RTPS 为 99.9。"
    fake_id = "BRD-K00000000 排名第一。"
    cases = {"honest": honest, "fake_drug": fake_drug,
             "fake_number": fake_number, "fake_brd": fake_id}
    verdicts = {k: verify_summary(v, mock)[0] for k, v in cases.items()}
    template = summarize(mock, use_llm=False)
    return {"verifier": verdicts,
            "honest_pass": verdicts["honest"],
            "hallucinations_caught": sum(1 for k in cases if k != "honest"
                                         and not verdicts[k]),
            "n_hallucination_cases": 3,
            "template_verified": template.get("verified")}


def main():
    queries = json.loads(QUERIES.read_text())["queries"]
    report = {"n_queries": len(queries)}
    report["mode_a_rules"] = run_rules(queries)
    report["mode_b_deepseek"] = run_llm(queries)
    report["engine_latency"] = engine_latency()
    try:
        report["http_latency"] = http_latency()
        report["concurrency"] = concurrency_test()
    except Exception as exc:  # noqa: BLE001
        report["http_error"] = str(exc)[:200]
    report["hallucination"] = hallucination_checks()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str))
    brief = {k: report[k] for k in ("mode_a_rules", "mode_b_deepseek", "engine_latency",
                                   "http_latency", "concurrency", "hallucination")
             if k in report}
    brief["mode_a_rules"] = {k: v for k, v in report["mode_a_rules"].items()
                             if k != "routed"}
    print(json.dumps(brief, indent=2, default=str))


if __name__ == "__main__":
    main()
