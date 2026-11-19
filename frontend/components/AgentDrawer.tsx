"use client";
import { useState } from "react";

export default function AgentDrawer() {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [answer, setAnswer] = useState<any>(null);
  const [useLLM, setUseLLM] = useState(false);

  async function run() {
    if (!text.trim()) return;
    setLoading(true);
    setAnswer(null);
    try {
      const res = await fetch("/api/v1/agent/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, use_llm: useLLM }),
      });
      setAnswer(await res.json());
    } catch (err: any) {
      setAnswer({ error: String(err) });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="agent-drawer">
      <header style={{ cursor: "pointer" }} onClick={() => setOpen(!open)}>
        <span>确定性 Agent 助手 {open ? "▾" : "▸"}</span>
        <span className="spacer" />
        <span className="small" style={{ opacity: 0.75 }}>{useLLM ? "LLM" : "0-LLM"}</span>
      </header>
      {open && (
        <div className="body">
          <textarea
            placeholder="例如：为 DKD 案例找可逆转的候选药；或查询 dexamethasone 的肾脏画像"
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="row" style={{ marginTop: 8 }}>
            <label className="small" style={{ margin: 0 }}>
              <input type="checkbox" checked={useLLM} onChange={(e) => setUseLLM(e.target.checked)} />{" "}
              使用 DeepSeek（需 API Key）
            </label>
            <span className="spacer" />
            <button onClick={run} disabled={loading}>{loading ? "解析中…" : "解析意图"}</button>
          </div>
          {answer && (
            <div style={{ marginTop: 10 }}>
              <div className="small muted">仅映射 SOP 与参数，所有数值由确定性后端计算。</div>
              <pre className="pre">{JSON.stringify(answer, null, 2)}</pre>
              {answer.sop_id === "SOP-6" && answer.params?.case_id && (
                <a href={`/cases`} className="small">前往案例库运行 →</a>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
