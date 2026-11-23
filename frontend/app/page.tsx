"use client";
import { useEffect, useRef } from "react";
import Link from "next/link";
import { useAgent } from "@/components/AgentContext";
import AgentResult from "@/components/AgentResult";
import ExampleCards from "@/components/ExampleCards";

const STATS = [
  ["21,299", "Compounds"],
  ["12,328", "L1000 Genes"],
  ["591,697", "Level-5 Profiles"],
  ["9,888", "IK-14 Scaffolds"],
  ["31,082", "Genetic Perturbs"],
  ["725", "CollecTRI TFs"],
];

const HOW_STEPS = [
  ["Match Workflow", "Identifies your task type (SOP-1 to SOP-6) using fixed rules, without AI guessing."],
  ["Standardize Inputs", "Converts gene symbols, drug names, kidney cohorts, or SMILES into database IDs."],
  ["Run Analysis", "Computes exact reversal scores, knockdown matches, or chemical similarity."],
  ["Safety Check & Report", "Flags nephrotoxic drugs (T-DIKI / DIRIL) and returns a traceable result table."],
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
    useLLM,
    setUseLLM,
    loading,
    result,
    error,
    focusTick,
    run,
    clearResult,
  } = useAgent();

  const consoleRef = useRef<HTMLTextAreaElement>(null);
  const heroRef = useRef<HTMLElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (focusTick > 0) {
      heroRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      consoleRef.current?.focus();
    }
  }, [focusTick]);

  useEffect(() => {
    if (result) {
      resultRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [result]);

  return (
    <>
      <section className="hero" ref={heroRef} id="agent-console">
        <div>
          <span className="hero-kicker">Deterministic SOP Engine · Zero Hallucination</span>
          <h1>NephroAgent</h1>
          <div className="muted" style={{ fontSize: 13 }}>
            Rule-governed kidney drug-repurposing assistant backed by K-PRL signatures and NephroSafe guardrails.
          </div>

          <div className="agent-box">
            <textarea
              ref={consoleRef}
              placeholder="Query cohorts, gene signatures, pathways, targets, compounds, or SMILES..."
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
                {loading ? "Executing..." : "Run Agent"}
              </button>
              <button
                type="button"
                className="ghost"
                onClick={() => {
                  setPrompt("");
                  clearResult();
                }}
              >
                Clear
              </button>
              <span className="spacer" />
              <label
                className="small"
                style={{ margin: 0, display: "flex", alignItems: "center", gap: 5 }}
              >
                <input
                  type="checkbox"
                  checked={useLLM}
                  onChange={(e) => setUseLLM(e.target.checked)}
                />
                DeepSeek slot parser (optional)
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

      <div className="grid cols-6" style={{ marginBottom: 12 }}>
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

      <div className="row" style={{ marginBottom: 8 }}>
        <h2 style={{ margin: 0, fontSize: 15 }}>Showcase Queries</h2>
        <span className="small muted">Click card to prefill, or Run ▶ to execute immediately</span>
      </div>
      <ExampleCards />

      <div ref={resultRef}>
        <AgentResult result={result} onRunSuggestion={(s) => run(s)} />
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
