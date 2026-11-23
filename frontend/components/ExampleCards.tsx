"use client";
import type { CSSProperties } from "react";
import { AGENT_EXAMPLES } from "@/lib/examples";
import { useAgent } from "@/components/AgentContext";

export default function ExampleCards() {
  const { fill, run, loading } = useAgent();

  return (
    <div className="example-grid">
      {AGENT_EXAMPLES.map((ex) => (
        <div
          key={ex.id}
          className="example-card"
          style={{ "--ex-color": ex.color } as CSSProperties}
          onClick={() => fill(ex.prompt)}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              fill(ex.prompt);
            }
          }}
        >
          <div className="row" style={{ justifyContent: "space-between", gap: 6 }}>
            <span className="badge blue" style={{ background: `${ex.color}18`, color: ex.color }}>
              {ex.sop}
            </span>
            <span className="small muted">Click to fill</span>
          </div>
          <div className="example-title">{ex.title}</div>
          <div className="example-sub">{ex.subtitle}</div>
          <div className="example-prompt" title={ex.prompt}>
            {ex.prompt}
          </div>
          <div className="example-foot">
            <span className="small muted">Deterministic SOP</span>
            <button
              type="button"
              className="mini"
              disabled={loading}
              onClick={(e) => {
                e.stopPropagation();
                run(ex.prompt);
              }}
            >
              Run ▶
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
