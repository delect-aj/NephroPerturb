"use client";
import type { CSSProperties } from "react";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useAgent } from "@/components/AgentContext";
import AgentResult from "@/components/AgentResult";
import { QUICK_EXAMPLES } from "@/lib/examples";

const STATS = [
  ["21,299", "Compounds"],
  ["12,328", "L1000 Genes"],
  ["591,697", "Level-5 Profiles"],
  ["9,888", "IK-14 Scaffolds"],
  ["31,082", "Genetic Perturbs"],
  ["6", "Agent Skills"],
];

const HOW_STEPS = [
  ["Select Skill & Plan", "Matches one of 6 scoped Skills and plans multi-step tool execution."],
  ["Execute & Reflect", "Runs deterministic scoring, detects high T-DIKI hits, and auto re-screens safe drugs."],
  ["Fetch Live Evidence", "Queries Europe PMC / PubMed & ClinicalTrials.gov with 7-day SQLite caching."],
  ["Verify & Report", "Audits every PMID, NCT ID, and score before rendering your traceable dossier."],
];

const EXPLORE_TILES = [
  ["/workbench", "Signature Workbench", "Multi-scale WTCS, XSum, Zhang & functional reversal with RenalConn weighting."],
  ["/pathway-tf", "Pathway & TF Search", "Query precomputed PROGENy, CollecTRI & renal pathology activity."],
  ["/target/?symbol=TGFBR1", "Target & Genetics", "Nephron compartment expression, targeting drugs & knockdown mimicry."],
  ["/compound/?id=dexamethasone", "Compound Explorer", "2D structure, K-PRL signature, T-DIKI v2 attribution & scaffold siblings."],
  ["/structure/?q=CC(%3DO)OC1%3DCC%3DCC%3DC1C(%3DO)O", "Structure Search", "2048-bit ECFP4 Tanimoto search & MoA inference from SMILES or ID."],
  ["/cases", "Disease Cohorts", "10 QC-validated human kidney biopsy cohorts across DKD, LN, IgAN, CKD & AKI."],
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
  const threadEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (focusTick > 0) {
      heroRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      consoleRef.current?.focus();
    }
  }, [focusTick]);

  useEffect(() => {
    if (turns.length > 0) {
      threadEndRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [turns.length, turns[turns.length - 1]?.steps?.length, turns[turns.length - 1]?.status]);

  const quickExamplesSection = (
    <section className="quick-examples" aria-label="Example Research Queries">
      <div className="quick-examples-head">
        <h2>Example Inputs</h2>
        <span className="small muted">
          Click any example to fill the Run Research box — edit if needed, then click Run Research
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
              title="Click to insert into Run Research box"
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
              Skill-Guided ReAct · Europe PMC &amp; ClinicalTrials
            </span>
          </div>

          <h1>NephroAgent</h1>
          <div className="muted" style={{ fontSize: 13 }}>
            Autonomous multi-step kidney drug-repurposing research agent: plans workflows, reflects on nephrotoxicity, searches PubMed &amp; trials, and verifies every claim.
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
              placeholder="Ask a multi-step research question (e.g. Find reversal drugs for DKD glomeruli, rescue toxic hits, and verify literature) or click an example below..."
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

      {/* Compact clickable examples right under Run Research when starting */}
      {turns.length === 0 && quickExamplesSection}

      {/* Multi-Turn Conversation Session Thread */}
      {turns.length > 0 && (
        <section className="session-thread" aria-label="Research Session Thread">
          <div className="row" style={{ marginBottom: 8 }}>
            <h2 style={{ margin: 0, fontSize: 15 }}>Active Research Session ({turns.length} turn{turns.length > 1 ? "s" : ""})</h2>
            <span className="small muted">Session memory tracks active cohorts, #1..#15 candidates, and verified PMIDs/NCTs</span>
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
          <div className="followup-bar" ref={threadEndRef}>
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
        </section>
      )}

      {turns.length > 0 && <div style={{ marginTop: 14 }}>{quickExamplesSection}</div>}

      {/* Platform Overview: KPI Stats & 4-Step Pipeline */}
      <div className="grid cols-6" style={{ marginBottom: 12, marginTop: 14 }}>
        {STATS.map(([v, l]) => (
          <div className="card kpi-card" key={l}>
            <div className="stat">{v}</div>
            <div className="stat-label">{l}</div>
          </div>
        ))}
      </div>

      <div className="how-strip">
        {HOW_STEPS.map(([title, desc], idx) => (
          <div className="how-step" key={title}>
            <div className="how-num">{idx + 1}</div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 12.5 }}>{title}</div>
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
