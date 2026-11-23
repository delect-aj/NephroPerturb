"use client";
import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { useAgent } from "@/components/AgentContext";
import AgentResult from "@/components/AgentResult";
import { AGENT_EXAMPLES } from "@/lib/examples";

export default function AgentDrawer() {
  const pathname = usePathname() || "/";
  const {
    prompt,
    setPrompt,
    useLLM,
    setUseLLM,
    open,
    setOpen,
    loading,
    result,
    error,
    focusTick,
    run,
  } = useAgent();
  const boxRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (open && pathname !== "/" && boxRef.current) {
      boxRef.current.focus();
    }
  }, [open, focusTick, pathname]);

  if (pathname === "/") return null;

  if (!open) {
    return (
      <button type="button" className="agent-pill" onClick={() => setOpen(true)}>
        Ask NephroAgent
      </button>
    );
  }

  return (
    <div className="agent-drawer">
      <header>
        <span>NephroAgent</span>
        <span className="spacer" />
        <span className="small" style={{ opacity: 0.85 }}>
          {useLLM ? "DeepSeek slots" : "0-LLM rules"}
        </span>
        <button
          type="button"
          className="mini ghost"
          style={{ marginLeft: 6, background: "rgba(255,255,255,0.16)", color: "#fff" }}
          onClick={() => setOpen(false)}
        >
          Minimize
        </button>
      </header>
      <div className="body">
        <textarea
          ref={boxRef}
          style={{ minHeight: 62 }}
          placeholder="Ask about cohorts, genes, pathways, drugs, or SMILES..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
              e.preventDefault();
              run();
            }
          }}
        />
        <div className="chip-row" style={{ marginTop: 6 }}>
          {AGENT_EXAMPLES.slice(0, 3).map((ex) => (
            <button
              key={ex.id}
              type="button"
              className="chip"
              onClick={() => setPrompt(ex.prompt)}
            >
              {ex.title}
            </button>
          ))}
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <label className="small" style={{ margin: 0, display: "flex", alignItems: "center", gap: 5 }}>
            <input
              type="checkbox"
              checked={useLLM}
              onChange={(e) => setUseLLM(e.target.checked)}
            />
            DeepSeek slot parser
          </label>
          <span className="spacer" />
          <button type="button" onClick={() => run()} disabled={loading}>
            {loading && <span className="spinner" />}
            {loading ? "Running..." : "Run Agent"}
          </button>
        </div>

        {error && (
          <div className="small" style={{ color: "var(--bad)", marginTop: 8 }}>
            {error}
          </div>
        )}

        {result && (
          <div style={{ marginTop: 8 }}>
            <AgentResult result={result} compact onRunSuggestion={(s) => run(s)} />
          </div>
        )}
      </div>
    </div>
  );
}
