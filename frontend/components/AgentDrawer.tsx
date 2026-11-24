"use client";
import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { useAgent } from "@/components/AgentContext";
import AgentResult from "@/components/AgentResult";

export default function AgentDrawer() {
  const pathname = usePathname() || "/";
  const {
    prompt,
    setPrompt,
    agentMode,
    setAgentMode,
    selectedSkill,
    setSelectedSkill,
    includeLiterature,
    setIncludeLiterature,
    skills,
    open,
    setOpen,
    loading,
    turns,
    error,
    focusTick,
    run,
    stop,
    newSession,
  } = useAgent();

  const [followUp, setFollowUp] = useState("");
  const boxRef = useRef<HTMLTextAreaElement>(null);
  const consoleSectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (focusTick > 0 && pathname !== "/") {
      setOpen(true);
      requestAnimationFrame(() => {
        consoleSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
        boxRef.current?.focus();
      });
    }
  }, [focusTick, pathname, setOpen]);

  if (pathname === "/") return null;

  return (
    <section
      className="hero hero-inline"
      ref={consoleSectionRef}
      id="inline-agent-console"
      aria-label="NephroAgent Inline Console"
    >
      <div className="row" style={{ gap: 8, marginBottom: open ? 6 : 0 }}>
        <span className="hero-kicker" style={{ marginBottom: 0 }}>
          Skill-Guided ReAct · Europe PMC &amp; ClinicalTrials
        </span>
        <strong style={{ fontSize: 15, color: "var(--ink)" }}>NephroAgent</strong>
        {turns.length > 0 && (
          <span className="badge blue">
            {turns.length} turn{turns.length > 1 ? "s" : ""}
          </span>
        )}
        <span className="spacer" />
        <button
          type="button"
          className="ghost mini"
          onClick={() => setOpen(!open)}
        >
          {open ? "Collapse Console ▴" : "Expand NephroAgent ▾"}
        </button>
      </div>

      {open && (
        <>
          {/* Skill Selector Strip */}
          <div className="skill-strip" role="group" aria-label="Select Agent Skill">
            <button
              type="button"
              className={`skill-pill ${selectedSkill === null ? "active" : ""}`}
              onClick={() => setSelectedSkill(null)}
            >
              Auto Skill
            </button>
            {skills.map((sk) => (
              <button
                key={sk.id}
                type="button"
                className={`skill-pill ${selectedSkill === sk.id ? "active" : ""}`}
                style={
                  selectedSkill === sk.id
                    ? { borderColor: sk.color, color: sk.color, background: `${sk.color}12` }
                    : undefined
                }
                title={sk.description}
                onClick={() => setSelectedSkill(selectedSkill === sk.id ? null : sk.id)}
              >
                {sk.short_label}
              </button>
            ))}
          </div>

          <div className="agent-box">
            <textarea
              ref={boxRef}
              placeholder="Ask a multi-step research question (e.g. Find reversal drugs for DKD glomeruli, rescue toxic hits, and verify literature) or click Ask Agent on any item below..."
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                  e.preventDefault();
                  run();
                }
              }}
            />
            <div className="agent-box-bar">
              <button type="button" onClick={() => run()} disabled={loading}>
                {loading && <span className="spinner" />}
                {loading ? "Researching..." : "Run Research"}
              </button>
              {loading && (
                <button type="button" className="ghost" onClick={stop}>
                  Stop
                </button>
              )}
              <button type="button" className="ghost" onClick={() => setPrompt("")}>
                Clear
              </button>
              {turns.length > 0 && (
                <button type="button" className="ghost" onClick={newSession}>
                  New Session
                </button>
              )}
              <span className="spacer" />
              <div className="mode-toggle" role="group" aria-label="Execution Mode">
                <button
                  type="button"
                  className={agentMode === "auto" ? "active" : ""}
                  onClick={() => setAgentMode("auto")}
                  title="Use DeepSeek ReAct planner + deterministic engine (auto-fallback if quota exceeded)"
                >
                  DeepSeek ReAct
                </button>
                <button
                  type="button"
                  className={agentMode === "fast" ? "active" : ""}
                  onClick={() => setAgentMode("fast")}
                  title="Run deterministic multi-step pipeline without LLM calls"
                >
                  0-LLM Multi-Step
                </button>
              </div>
              <label className="small" style={{ margin: 0, display: "flex", alignItems: "center", gap: 4 }}>
                <input
                  type="checkbox"
                  checked={includeLiterature}
                  onChange={(e) => setIncludeLiterature(e.target.checked)}
                />
                Literature &amp; Trials
              </label>
            </div>
          </div>

          {error && (
            <div className="small" style={{ color: "var(--bad)", marginTop: 6 }}>
              {error}
            </div>
          )}

          {turns.length > 0 && (
            <div className="session-thread" style={{ marginTop: 12 }} aria-label="Research Session Thread">
              <div className="row" style={{ marginBottom: 8 }}>
                <h2 style={{ margin: 0, fontSize: 14.5 }}>
                  Active Research Session ({turns.length} turn{turns.length > 1 ? "s" : ""})
                </h2>
                <span className="spacer" />
                <button type="button" className="ghost mini" onClick={newSession}>
                  Reset Session
                </button>
              </div>
              {turns.map((turn, idx) => (
                <div key={turn.id} className="turn-block">
                  <div className="user-bubble">
                    <span className="badge blue">Turn {idx + 1}</span>
                    <span>{turn.query}</span>
                  </div>
                  <AgentResult result={turn} onRunSuggestion={(s) => run(s)} />
                </div>
              ))}
              <div className="followup-bar">
                <input
                  type="text"
                  placeholder="Ask a follow-up in this session (e.g. Compare #1 and #2, or Check trials for #3)..."
                  value={followUp}
                  onChange={(e) => setFollowUp(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && followUp.trim() && !loading) {
                      e.preventDefault();
                      const q = followUp.trim();
                      setFollowUp("");
                      run(q);
                    }
                  }}
                />
                <button
                  type="button"
                  disabled={loading || !followUp.trim()}
                  onClick={() => {
                    const q = followUp.trim();
                    if (!q) return;
                    setFollowUp("");
                    run(q);
                  }}
                >
                  {loading ? "Running..." : "Send Follow-Up"}
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
