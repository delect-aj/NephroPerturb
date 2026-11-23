"use client";
import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { useAgent } from "@/components/AgentContext";
import AgentResult from "@/components/AgentResult";
import { RESEARCH_PLAYBOOKS } from "@/lib/examples";

export default function AgentDrawer() {
  const pathname = usePathname() || "/";
  const {
    prompt,
    setPrompt,
    agentMode,
    setAgentMode,
    includeLiterature,
    setIncludeLiterature,
    statusInfo,
    open,
    setOpen,
    loading,
    turns,
    result,
    error,
    focusTick,
    run,
    stop,
    newSession,
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
        Ask NephroAgent{turns.length ? ` (${turns.length})` : ""}
      </button>
    );
  }

  const quota = statusInfo?.quota;

  return (
    <div className="agent-drawer">
      <header>
        <span>NephroAgent</span>
        {turns.length > 0 && (
          <span className="badge" style={{ background: "rgba(255,255,255,0.18)", color: "#fff" }}>
            Turn {turns.length}
          </span>
        )}
        <span className="spacer" />
        <span className="small" style={{ opacity: 0.85 }}>
          {agentMode === "fast"
            ? "0-LLM"
            : quota
              ? `${quota.remaining_hourly}/${quota.hourly_limit}/hr`
              : "ReAct"}
        </span>
        {turns.length > 0 && (
          <button
            type="button"
            className="mini ghost"
            style={{ marginLeft: 4, background: "rgba(255,255,255,0.14)", color: "#fff" }}
            onClick={newSession}
          >
            New
          </button>
        )}
        <button
          type="button"
          className="mini ghost"
          style={{ marginLeft: 4, background: "rgba(255,255,255,0.16)", color: "#fff" }}
          onClick={() => setOpen(false)}
        >
          Minimize
        </button>
      </header>
      <div className="body">
        <textarea
          ref={boxRef}
          style={{ minHeight: 58 }}
          placeholder="Ask about cohorts, drugs, comparisons (#1 vs #2), or literature..."
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
          {RESEARCH_PLAYBOOKS.slice(0, 2).map((pb) => (
            <button
              key={pb.id}
              type="button"
              className="chip"
              onClick={() => run(pb.prompt, { skillId: pb.skillId })}
            >
              {pb.badge}
            </button>
          ))}
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <label className="small" style={{ margin: 0, display: "flex", alignItems: "center", gap: 4 }}>
            <input
              type="checkbox"
              checked={agentMode === "auto"}
              onChange={(e) => setAgentMode(e.target.checked ? "auto" : "fast")}
            />
            DeepSeek ReAct
          </label>
          <label className="small" style={{ margin: 0, display: "flex", alignItems: "center", gap: 4 }}>
            <input
              type="checkbox"
              checked={includeLiterature}
              onChange={(e) => setIncludeLiterature(e.target.checked)}
            />
            PubMed/Trials
          </label>
          <span className="spacer" />
          {loading ? (
            <button type="button" className="ghost mini" onClick={stop}>
              Stop
            </button>
          ) : (
            <button type="button" onClick={() => run()}>
              Run
            </button>
          )}
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
