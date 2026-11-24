"use client";
import type { CSSProperties } from "react";
import Link from "next/link";
import { useAgent } from "@/components/AgentContext";
import { AUTO_ROUTING_RULES, SKILLS_CATALOG } from "@/lib/skillsCatalog";

export default function SkillsPage() {
  const { fill } = useAgent();

  return (
    <>
      <div className="page-head">
        <h1>6 Agent Skills &amp; Execution Logic</h1>
        <span className="badge blue">Modular ReAct Playbooks</span>
        <span className="spacer" />
        <Link href="/" prefetch={false}>
          <button type="button" className="ghost mini">
            ← Back to Agent Console
          </button>
        </Link>
      </div>
      <div className="sub">
        Every research query is routed deterministically to one focused Skill with scoped tools, safety reflection rules, and a fixed 4-section synthesis format.
      </div>

      {/* How Auto Skill Chooses a Skill */}
      <section className="card" style={{ marginBottom: 14 }}>
        <div className="row" style={{ marginBottom: 8 }}>
          <h2 style={{ margin: 0 }}>How Auto Skill Routes Your Query</h2>
          <span className="small muted">Zero-LLM rule router runs in &lt;1 ms before any model call</span>
        </div>
        <div className="grid cols-4">
          {AUTO_ROUTING_RULES.map((r) => (
            <div key={r.priority} className="route-step-card">
              <div className="row" style={{ gap: 7, marginBottom: 4 }}>
                <span className="how-num">{r.priority}</span>
                <strong style={{ fontSize: 12.8 }}>{r.title}</strong>
              </div>
              <div className="small muted" style={{ lineHeight: 1.45 }}>
                {r.rule}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Detailed Step-by-Step Guide for Each of the 6 Skills */}
      <div className="row" style={{ marginBottom: 8 }}>
        <h2 style={{ margin: 0, fontSize: 15 }}>Step-by-Step Breakdown of Each Skill</h2>
        <span className="small muted">Click &quot;Try Example ↗&quot; on any Skill to test it directly in the Research Assistant</span>
      </div>

      <div className="skills-catalog-grid">
        {SKILLS_CATALOG.map((sk, idx) => (
          <section
            key={sk.id}
            id={sk.id}
            className="card skill-doc-card"
            style={{ "--skill-color": sk.color } as CSSProperties}
          >
            <div className="row" style={{ gap: 8, marginBottom: 6 }}>
              <span
                className="badge"
                style={{ background: `${sk.color}18`, color: sk.color }}
              >
                Skill {idx + 1} · {sk.shortLabel}
              </span>
              <span className="badge grey mono">{sk.id}</span>
              <span className="badge grey">Max {sk.maxSteps} steps</span>
              <span className="spacer" />
              <button
                type="button"
                className="ghost mini"
                onClick={() => fill(sk.examplePrompt, sk.id)}
                title="Load this Skill and example prompt into the Research Assistant"
              >
                Try Example ↗
              </button>
            </div>

            <h3 className="skill-doc-title">{sk.name}</h3>
            <div className="skill-when-box">
              <strong>When selected:</strong> {sk.whenUsed}
            </div>

            <div className="skill-steps-list">
              {sk.workflow.map((st) => (
                <div key={st.step} className="skill-step-row">
                  <div className="skill-step-num" style={{ background: sk.color }}>
                    {st.step}
                  </div>
                  <div className="skill-step-body">
                    <div className="skill-step-head">
                      <strong>{st.title}</strong>
                      <span className="skill-step-tools">
                        {st.tools.map((t) => (
                          <code key={t} className="inline-code">
                            {t}
                          </code>
                        ))}
                      </span>
                    </div>
                    <div className="small muted" style={{ lineHeight: 1.45 }}>
                      {st.logic}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <div className="skill-doc-foot">
              <div className="small">
                <strong style={{ color: "var(--ink)" }}>Fixed Report Sections:</strong>{" "}
                <span className="muted">{sk.outputSections.join("  ->  ")}</span>
              </div>
              <div className="small" style={{ marginTop: 4 }}>
                <strong style={{ color: "var(--ink)" }}>Allowed Tools:</strong>{" "}
                <span className="mono muted">{sk.allowedTools.join(", ")}</span>
              </div>
            </div>
          </section>
        ))}
      </div>
    </>
  );
}
