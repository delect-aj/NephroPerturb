"use client";
import { useEffect, useRef } from "react";
import Link from "next/link";
import { useAgent } from "@/components/AgentContext";
import AgentResult from "@/components/AgentResult";
import ExampleCards from "@/components/ExampleCards";

const STATS = [
  ["21,299", "Small Molecules"],
  ["12,328", "L1000 Genes"],
  ["591,697", "Level-5 Signatures"],
  ["9,888", "InChIKey-14 Scaffolds"],
  ["31,082", "Genetic Perturbations"],
  ["725", "CollecTRI TFs"],
];

const HOW_STEPS = [
  ["Parse intent", "Rule router matches SOP-1..6 or optional DeepSeek extracts slot JSON."],
  ["Map to SOP", "Resolves gene aliases, cohort IDs, compound names, or SMILES deterministically."],
  ["Call fixed tool", "Executes the exact scoring, mimicry, or ECFP4 similarity engine endpoint."],
  ["Safety & template", "Annotates High T-DIKI / DIRIL flags and builds a verified template summary."],
];

const EXPLORE_TILES = [
  ["/workbench", "Signature Workbench", "Multi-scale WTCS, XSum, Zhang & functional reversal with 4D RenalConn weighting."],
  ["/pathway-tf", "Pathway & TF Search", "Query precomputed PROGENy, CollecTRI & renal pathology activity matrices."],
  ["/target/?symbol=TGFBR1", "Target & Genetics", "Single-cell kidney expression, targeting drugs, and LINCS knockdown mimicry."],
  ["/compound/?id=dexamethasone", "Compound Explorer", "2D structure, K-PRL signature, T-DIKI v2 attribution & scaffold siblings."],
  ["/structure/?q=CC(%3DO)OC1%3DCC%3DCC%3DC1C(%3DO)O", "Structure Search", "ECFP4 2048-bit Tanimoto scan & MoA inference from SMILES or drug IDs."],
  ["/cases", "Disease Cohorts", "10 QC'd human kidney biopsy cohorts across DKD, LN, IgAN, CKD, and AKI."],
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
          <h1>NephroAgent — deterministic kidney drug-repurposing assistant</h1>
          <div className="muted" style={{ fontSize: 13.5 }}>
            No open-ended AI guessing: rules map your question directly to 6 pre-validated SOP tools and template summaries.
          </div>

          <div className="agent-box">
            <textarea
              ref={consoleRef}
              placeholder="Ask in plain English or Chinese, e.g. Find reversal drugs for the DKD glomeruli case"
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
                {loading ? "Executing SOP..." : "Run Agent"}
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
                style={{ margin: 0, display: "flex", alignItems: "center", gap: 6 }}
              >
                <input
                  type="checkbox"
                  checked={useLLM}
                  onChange={(e) => setUseLLM(e.target.checked)}
                />
                Use DeepSeek for parameter extraction (requires API key)
              </label>
            </div>
          </div>
          {error && (
            <div className="small" style={{ color: "var(--bad)", marginTop: 8 }}>
              {error}
            </div>
          )}
        </div>

        <div style={{ display: "flex", justifyContent: "center" }}>
          <img
            src="/hero.svg"
            alt="NephroPerturb kidney perturbation network illustration"
            className="hero-art"
          />
        </div>
      </section>

      <div className="how-strip">
        {HOW_STEPS.map(([title, desc], idx) => (
          <div className="how-step" key={title}>
            <div className="how-num">{idx + 1}</div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 13 }}>{title}</div>
              <div className="small muted">{desc}</div>
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginBottom: 8 }} className="row">
        <h2 style={{ margin: 0, fontSize: 16 }}>Try an example</h2>
        <span className="small muted">
          Click any card to fill the Agent console, or press Run ▶ to execute immediately
        </span>
      </div>
      <ExampleCards />

      <div ref={resultRef}>
        <AgentResult result={result} onRunSuggestion={(s) => run(s)} />
      </div>

      <div className="grid cols-3" style={{ marginTop: 22 }}>
        {STATS.map(([v, l]) => (
          <div className="card" key={l}>
            <div className="stat">{v}</div>
            <div className="stat-label">{l}</div>
          </div>
        ))}
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <h2>Explore the knowledge base</h2>
        <div className="grid cols-3">
          {EXPLORE_TILES.map(([href, title, desc]) => (
            <Link
              key={href}
              href={href}
              style={{
                display: "block",
                padding: 12,
                borderRadius: 10,
                border: "1px solid var(--line)",
                background: "var(--panel-soft)",
                color: "var(--ink)",
              }}
            >
              <div style={{ fontWeight: 700, color: "var(--accent)", marginBottom: 4 }}>
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
