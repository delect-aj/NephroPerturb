"use client";
import type { CSSProperties } from "react";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useAgent } from "@/components/AgentContext";
import AgentResult from "@/components/AgentResult";
import { QUICK_EXAMPLES } from "@/lib/examples";

const STATS: Array<[string, string, string?]> = [
  ["21,299", "Compounds"],
  ["12,328", "Measured Genes"],
  ["591,697", "Perturbation Profiles"],
  ["9,888", "Unique Scaffolds"],
  ["31,082", "Genetic Perturbations"],
  ["6", "Agent Skills", "/skills"],
];

const HOW_STEPS = [
  ["1. Workflow Routing", "Matches your question to a specialized workflow for disease cohorts, targets, chemical structures, or drug comparisons."],
  ["2. Scoring & Safety Filtering", "Ranks 21,299 compounds by disease-signature reversal and automatically filters out candidates with high predicted nephrotoxicity."],
  ["3. Literature & Trial Retrieval", "Retrieves peer-reviewed studies from Europe PMC / PubMed and registered clinical studies from ClinicalTrials.gov."],
  ["4. Citation & Data Verification", "Cross-checks every score, compound ID, PubMed ID, and clinical trial number against source records before generating the report."],
];

const EXPLORE_TILES = [
  ["/workbench", "Signature Workbench", "Rank 21,299 compounds by multi-scale signature reversal and renal safety weighting."],
  ["/pathway-tf", "Pathway & TF Search", "Screen compounds modulating PROGENy signaling pathways, CollecTRI transcription factors, and renal pathology modules."],
  ["/target/?symbol=TGFBR1", "Target & Genetics", "Explore single-cell nephron expression, direct targeting drugs, and genetic knockdown mimicry."],
  ["/compound/?id=dexamethasone", "Compound Explorer", "Inspect 2D chemical structures, kidney perturbation profiles, nephrotoxicity risk attribution, and shared-scaffold analogs."],
  ["/structure/?q=CC(%3DO)OC1%3DCC%3DCC%3DC1C(%3DO)O", "Structure Search", "Search 21,299 compounds by 2D structural similarity (ECFP4 Tanimoto) and infer mechanism of action."],
  ["/cases", "Disease Cohorts", "Browse 10 curated human kidney biopsy transcriptomic cohorts across DKD, LN, IgAN, CKD, and AKI."],
];

export default function Home() {
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
    loading,
    turns,
    error,
    focusTick,
    fill,
    run,
    stop,
    newSession,
  } = useAgent();

  const [followUp, setFollowUp] = useState("");
  const consoleRef = useRef<HTMLTextAreaElement>(null);
  const heroRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (focusTick > 0) {
      heroRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      consoleRef.current?.focus();
    }
  }, [focusTick]);

  const quickExamplesSection = (
    <section className="quick-examples" aria-label="Example Research Queries">
      <div className="quick-examples-head">
        <h2>Example Inputs</h2>
        <span className="small muted">
          Click any example to populate the search box — edit if needed, then click Run Research
        </span>
      </div>
      <div className="quick-example-grid">
        {QUICK_EXAMPLES.map((ex) => {
          const isFilled = prompt.trim() === ex.prompt.trim();
          return (
            <button
              key={ex.id}
              type="button"
              className={`quick-example-card ${isFilled ? "filled" : ""}`}
              style={{ "--ex-color": ex.color } as CSSProperties}
              onClick={() => fill(ex.prompt, ex.skillId)}
              title="Click to insert into the Run Research box"
            >
              <div className="quick-example-top">
                <span className="badge" style={{ background: `${ex.color}18`, color: ex.color }}>
                  {ex.category}
                </span>
                <span className="quick-fill-hint">{isFilled ? "Filled ✓" : "Fill ↗"}</span>
              </div>
              <div className="quick-example-title">{ex.title}</div>
              <div className="quick-example-prompt">{ex.prompt}</div>
            </button>
          );
        })}
      </div>
    </section>
  );

  return (
    <>
      <section className="hero" ref={heroRef} id="agent-console">
        <div>
          <div className="row" style={{ gap: 6, marginBottom: 6 }}>
            <span className="hero-kicker" style={{ marginBottom: 0 }}>
              Kidney Drug Repurposing · Nephrotoxicity Assessment · Literature Synthesis
            </span>
          </div>

          <h1>NephroAgent</h1>
          <div className="muted" style={{ fontSize: 13 }}>
            Multi-step research assistant for kidney drug discovery — integrates transcriptomic reversal scoring, NephroSafe nephrotoxicity assessment, and live PubMed &amp; ClinicalTrials.gov evidence.
          </div>

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
                style={selectedSkill === sk.id ? { borderColor: sk.color, color: sk.color, background: `${sk.color}12` } : undefined}
                title={sk.description}
                onClick={() => setSelectedSkill(selectedSkill === sk.id ? null : sk.id)}
              >
                {sk.short_label}
              </button>
            ))}
          </div>

          <div className="agent-box">
            <textarea
              ref={consoleRef}
              placeholder="Enter a kidney drug discovery question (e.g., identify reversal drugs for DKD glomeruli, evaluate tacrolimus nephrotoxicity, or compare two candidates)..."
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
                  title="Multi-step AI reasoning with integrated literature review"
                >
                  AI Reasoning (ReAct)
                </button>
                <button
                  type="button"
                  className={agentMode === "fast" ? "active" : ""}
                  onClick={() => setAgentMode("fast")}
                  title="Instant rule-based pipeline without LLM calls"
                >
                  Rule-Based Fast
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
        </div>

        <div style={{ display: "flex", justifyContent: "center" }}>
          <img
            src="/hero.svg"
            alt="NephroPerturb kidney perturbation network"
            width={440}
            height={289}
            className="hero-art"
          />
        </div>
      </section>

      {/* Compact clickable examples always pinned directly below Run Research */}
      {quickExamplesSection}

      {/* Multi-Turn Conversation Session Thread */}
      {turns.length > 0 && (
        <section className="session-thread" aria-label="Research Session Thread">
          <div className="row" style={{ marginBottom: 8 }}>
            <h2 style={{ margin: 0, fontSize: 15 }}>Active Research Session ({turns.length} turn{turns.length > 1 ? "s" : ""})</h2>
            <span className="small muted">Follow-up questions can reference ranked candidates (e.g., #1, #2) and active disease cohorts</span>
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

          {/* Multi-turn follow-up bar */}
          <div className="followup-bar">
            <input
              type="text"
              placeholder="Ask a follow-up question in this session (e.g., Compare #1 and #2, or Check clinical trials for #3)..."
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
        </section>
      )}

      {/* Platform Overview: KPI Stats & 4-Step Pipeline */}
      <div className="grid cols-6" style={{ marginBottom: 12, marginTop: 14 }}>
        {STATS.map(([v, l, href]) =>
          href ? (
            <Link key={l} href={href} prefetch={false} className="card kpi-card kpi-link" title="Explore all 6 Agent Skills and step-by-step workflows">
              <div className="stat">{v}</div>
              <div className="stat-label">
                {l} <span className="kpi-arrow">→</span>
              </div>
            </Link>
          ) : (
            <div className="card kpi-card" key={l}>
              <div className="stat">{v}</div>
              <div className="stat-label">{l}</div>
            </div>
          )
        )}
      </div>

      <div className="how-strip">
        {HOW_STEPS.map(([title, desc], idx) => (
          <div className="how-step" key={title}>
            <div className="how-num">{idx + 1}</div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 12.5 }}>{title.replace(/^\d+\.\s*/, "")}</div>
              <div className="small muted">{desc}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <h2>Knowledge Base Modules</h2>
        <div className="grid cols-3">
          {EXPLORE_TILES.map(([href, title, desc]) => (
            <Link
              key={href}
              href={href}
              prefetch={false}
              style={{
                display: "block",
                padding: 10,
                borderRadius: 8,
                border: "1px solid var(--line)",
                background: "var(--panel-soft)",
                color: "var(--ink)",
              }}
            >
              <div style={{ fontWeight: 700, color: "var(--accent)", fontSize: 13, marginBottom: 2 }}>
                {title} →
              </div>
              <div className="small muted">{desc}</div>
            </Link>
          ))}
        </div>
      </div>
    </>
  );
}
