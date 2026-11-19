#!/usr/bin/env python
"""BM-4: deterministic engine latency and 0-LLM SOP routing accuracy."""
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))
from common import paths  # noqa: E402

OUT = ROOT / "benchmarks" / "outputs"

QUERIES = [
    ("为 DKD 案例找逆转药物", "SOP-6"),
    ("运行狼疮肾炎案例", "SOP-6"),
    ("看看 IgAN 队列", "SOP-6"),
    ("AKI 标准签名跑一下", "SOP-6"),
    ("CKD 纤维化案例", "SOP-6"),
    ("FSGS 有哪些候选", "SOP-6"),
    ("输入 SMILES 推断机制", "SOP-5"),
    ("这个结构 CC(=O)OC1=CC=CC=C1C(=O)O 像什么药", "SOP-5"),
    ("BRD-K81418486 的 MoA 是什么", "SOP-5"),
    ("抑制 TGFb 和 SMAD3，激活 PPARA 找药", "SOP-3"),
    ("查一下 NFKB1 通路候选", "SOP-3"),
    ("需要抑制 STAT3 的药物", "SOP-3"),
    ("HIF1A 激活剂有哪些", "SOP-3"),
    ("靶向 TGFBR1 的药物和敲除模拟", "SOP-4"),
    ("APOL1 的遗传扰动", "SOP-4"),
    ("JAK2 靶点", "SOP-4"),
    ("HAVCR1 基因敲除签名", "SOP-4"),
    ("dexamethasone 的肾脏画像", "SOP-2"),
    ("查询 sirolimus 详情", "SOP-2"),
    ("这个药物的 MoA 和安全信息", "SOP-2"),
]


def bench(fn, n=20):
    times = []
    for _ in range(n):
        start = time.perf_counter()
        fn()
        times.append((time.perf_counter() - start) * 1000)
    times.sort()
    return {"p50_ms": round(statistics.median(times), 1),
            "p95_ms": round(times[int(len(times) * 0.95) - 1], 1),
            "min_ms": round(times[0], 1)}


def main():
    from app.agent import route
    from app.core.store import get_store
    from app.engine.scoring import score_pathway_tf, score_signature
    OUT.mkdir(parents=True, exist_ok=True)
    store = get_store()

    up = ["COL1A1", "COL3A1", "FN1", "TGFB1", "SERPINE1", "LCN2", "HAVCR1"]
    down = ["NPHS1", "NPHS2", "PODXL", "WT1", "PPARA", "PPARGC1A", "CPT1A"]
    score_signature(up, down, top_k=10)  # warm caches

    latency = {
        "signature": bench(lambda: score_signature(up, down, top_k=20), n=10),
        "pathway_tf": bench(lambda: score_pathway_tf({"SMAD3": -1, "PPARA": 1}, top_k=10), n=10),
        "compound": bench(lambda: store.find_compound("dexamethasone"), n=20),
        "genetic_lookup": bench(lambda: store.genetic_index_map(), n=10),
    }

    correct = 0
    details = []
    for text, expected in QUERIES:
        result = route(text, use_llm=False)
        ok = result["sop_id"] == expected
        correct += int(ok)
        details.append({"text": text, "expected": expected,
                        "predicted": result["sop_id"], "correct": ok})
    accuracy = correct / len(QUERIES)
    payload = {"latency": latency,
               "agent": {"n": len(QUERIES), "accuracy": accuracy, "details": details},
               "targets": {"signature_p95_ms": 2000, "agent_accuracy": 0.95}}
    (OUT / "bm4_latency_agent.json").write_text(json.dumps(payload, indent=2))
    print(f"[bm4] latency {latency}")
    print(f"[bm4] SOP routing accuracy {accuracy:.2%} ({correct}/{len(QUERIES)})")
    print(f"[bm4] wrote {OUT / 'bm4_latency_agent.json'}")


if __name__ == "__main__":
    main()
