"use client";
import type { CSSProperties } from "react";
import { useState } from "react";
import Link from "next/link";
import { useAgent } from "@/components/AgentContext";
import {
  SHARED_SAFEGUARDS,
  SKILLS_CATALOG,
} from "@/lib/skillsCatalog";

function stageBadgeClass(tag?: string): string {
  switch (tag) {
    case "Auto-Reflect":
      return "stage-tag stage-reflect";
    case "Evidence":
      return "stage-tag stage-evidence";
    case "Verify & Write":
      return "stage-tag stage-verify";
    default:
      return "stage-tag stage-compute";
  }
}

export default function SkillsPage() {
  const { fill } = useAgent();
  const [activeFilter, setActiveFilter] = useState<string>("all");

  const visibleSkills =
    activeFilter === "all"
      ? SKILLS_CATALOG
      : SKILLS_CATALOG.filter((s) => s.id === activeFilter);

  return (
    <>
      {/* Hero Banner */}
      <section className="skills-hero">
        <div className="skills-hero-top">
          <div>
            <span className="hero-kicker" style={{ marginBottom: 6 }}>
              NephroAgent Architecture · 6 Modular ReAct Skills
            </span>
            <h1 className="skills-hero-title">Agent Skills &amp; Step-by-Step Logic</h1>
            <p className="skills-hero-sub">
              Every query is routed deterministically to one focused Skill with scoped tools, automatic nephrotoxicity reflection, and a verified 4-section synthesis report.
            </p>
          </div>
          <Link href="/" prefetch={false} style={{ flexShrink: 0 }}>
            <button type="button" className="ghost">
              ← Back to Agent Console
            </button>
          </Link>
        </div>

        {/* Interactive Skill Filter Strip */}
        <div className="skills-filter-strip" role="tablist" aria-label="Filter Agent Skills">
          <button
            type="button"
            role="tab"
            aria-selected={activeFilter === "all"}
            className={`skill-pill ${activeFilter === "all" ? "active" : ""}`}
            onClick={() => setActiveFilter("all")}
          >
            All 6 Skills
          </button>
          {SKILLS_CATALOG.map((sk) => {
            const isActive = activeFilter === sk.id;
            return (
              <button
                key={sk.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                className={`skill-pill ${isActive ? "active" : ""}`}
                style={
                  isActive
                    ? { borderColor: sk.color, color: sk.color, background: `${sk.color}14` }
                    : undefined
                }
                onClick={() => setActiveFilter(isActive ? "all" : sk.id)}
              >
                <span className="skill-dot" style={{ background: sk.color }} />
                {sk.shortLabel}
              </button>
            );
          })}
        </div>
      </section>

      {/* Step-by-Step Breakdown Cards */}
      <div className="row" style={{ marginBottom: 9 }}>
        <h2 style={{ margin: 0, fontSize: 15 }}>
          {activeFilter === "all"
            ? "Step-by-Step Logic for All 6 Skills"
            : `Focused View: ${visibleSkills[0]?.name}`}
        </h2>
        <span className="small muted">
          Click &quot;Try Example ↗&quot; to preload that Skill and prompt into the Research Assistant
        </span>
        {activeFilter !== "all" && (
          <>
            <span className="spacer" />
            <button type="button" className="ghost mini" onClick={() => setActiveFilter("all")}>
              Show all 6 Skills
            </button>
          </>
        )}
      </div>

      <div className={`skills-catalog-grid ${visibleSkills.length === 1 ? "single" : ""}`}>
        {visibleSkills.map((sk) => {
          const origIdx = SKILLS_CATALOG.findIndex((x) => x.id === sk.id) + 1;
          return (
            <article
              key={sk.id}
              id={sk.id}
              className="card skill-doc-card"
              style={{ "--skill-color": sk.color } as CSSProperties}
            >
              {/* Colored Card Header */}
              <div className="skill-doc-header">
                <div className="row" style={{ gap: 6, marginBottom: 6 }}>
                  <span
                    className="badge"
                    style={{ background: `${sk.color}1a`, color: sk.color }}
                  >
                    Skill {origIdx} · {sk.shortLabel}
                  </span>
                  <span className="badge grey mono">{sk.id}</span>
                  <span className="badge grey">Max {sk.maxSteps} steps</span>
                  <span className="spacer" />
                  <button
                    type="button"
                    className="ghost mini"
                    onClick={() => fill(sk.examplePrompt, sk.id)}
                    title="Open Research Assistant prefilled with this Skill's example"
                  >
                    Try Example ↗
                  </button>
                </div>
                <h3 className="skill-doc-title">{sk.name}</h3>
                <div className="skill-when-line">
                  <strong>Best for:</strong> {sk.whenUsed}
                </div>
              </div>

              {/* Connected Vertical Step Timeline */}
              <div className="skill-timeline">
                {sk.workflow.map((st, sIdx) => (
                  <div key={st.step} className="skill-tl-row">
                    <div className="skill-tl-rail">
                      <div className="skill-step-num" style={{ background: sk.color }}>
                        {st.step}
                      </div>
                      {sIdx < sk.workflow.length - 1 && (
                        <div className="skill-tl-line" style={{ background: `${sk.color}30` }} />
                      )}
                    </div>
                    <div className="skill-tl-content">
                      <div className="skill-step-head">
                        <strong>{st.title}</strong>
                        {st.stageTag && (
                          <span className={stageBadgeClass(st.stageTag)}>{st.stageTag}</span>
                        )}
                      </div>
                      <div className="skill-step-desc">{st.logic}</div>
                      {st.tools.length > 0 && (
                        <div className="skill-step-tools">
                          {st.tools.map((t) => (
                            <code key={t} className="tool-chip">
                              {t}
                            </code>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {/* Structured Report Blueprint + Allowed Tools */}
              <div className="skill-doc-foot">
                <div className="skill-foot-label">Fixed 4-Section Report Blueprint</div>
                <div className="skill-section-pills">
                  {sk.outputSections.map((sec) => (
                    <span key={sec} className="section-pill">
                      {sec}
                    </span>
                  ))}
                </div>
                <div className="skill-tools-summary">
                  <span className="skill-foot-label" style={{ marginBottom: 0 }}>
                    Tool Allowlist ({sk.allowedTools.length}):
                  </span>{" "}
                  <span className="mono muted">{sk.allowedTools.join(" · ")}</span>
                </div>
              </div>
            </article>
          );
        })}
      </div>

      {/* Shared Execution & Verification Safeguards */}
      <section className="card" style={{ marginTop: 14 }}>
        <div className="row" style={{ marginBottom: 8 }}>
          <h2 style={{ margin: 0 }}>Shared Safeguards Across All 6 Skills</h2>
          <span className="small muted">Enforced identically in DeepSeek ReAct and 0-LLM Multi-Step modes</span>
        </div>
        <div className="grid cols-4">
          {SHARED_SAFEGUARDS.map((g) => (
            <div key={g.title} className="safeguard-tile">
              <div className="safeguard-title">{g.title}</div>
              <div className="small muted" style={{ lineHeight: 1.45 }}>
                {g.detail}
              </div>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
