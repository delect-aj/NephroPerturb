"use client";
import Link from "next/link";

function dikiBadge(tier?: string) {
  if (!tier || tier === "NA") return <span className="badge grey">NA</span>;
  const cls = tier === "High" ? "red" : tier === "Moderate" ? "amber" : "green";
  return <span className={`badge ${cls}`}>{tier}</span>;
}

function dirilBadge(label?: string) {
  if (!label || label === "—") return <span className="badge grey">—</span>;
  return (
    <span className={`badge ${label === "Positive" ? "red" : "green"}`}>
      {label}
    </span>
  );
}

export default function AgentResult({
  result,
  compact = false,
  onRunSuggestion,
}: {
  result: any;
  compact?: boolean;
  onRunSuggestion?: (prompt: string) => void;
}) {
  if (!result) return null;
  const steps = result.steps || [];
  const facts = result.facts || [];
  const cols = result.table?.columns || [];
  const rows = result.table?.rows || [];
  const links = result.links || [];
  const suggestions = result.suggestions || [];

  const statusLabel: Record<string, string> = {
    ok: "Executed",
    needs_input: "Needs input",
    out_of_scope: "Out of scope",
    error: "Error",
  };

  return (
    <div className="card" style={compact ? { padding: 12, boxShadow: "none" } : { marginTop: 18 }}>
      <div className="row" style={{ gap: 8 }}>
        <span className={`badge status-${result.status || "ok"}`}>
          {statusLabel[result.status] || result.status}
        </span>
        {result.sop_id && (
          <span className="badge blue">
            {result.sop_id} · {result.sop_title}
          </span>
        )}
        <span className="badge grey">
          {result.mode === "deepseek" ? "DeepSeek params" : "Rules · 0-LLM"}
        </span>
        <span className="spacer" />
        {result.elapsed_ms != null && (
          <span className="small muted mono">{result.elapsed_ms} ms</span>
        )}
      </div>

      {steps.length > 0 && (
        <div className="timeline">
          {steps.map((s: any, idx: number) => (
            <div
              key={`${idx}-${s.name}`}
              className={`step ${s.status === "error" ? "step-error" : s.status === "skipped" ? "step-skipped" : ""}`}
            >
              <div className="row" style={{ gap: 8 }}>
                <strong>
                  {idx + 1}. {s.name}
                </strong>
                <span className="badge grey mono">{s.tool}</span>
                <span className="spacer" />
                {s.ms != null && <span className="small muted mono">{s.ms} ms</span>}
              </div>
              {s.detail && <div className="small muted" style={{ marginTop: 3 }}>{s.detail}</div>}
            </div>
          ))}
        </div>
      )}

      {result.summary && <div className="summary-box">{result.summary}</div>}

      {facts.length > 0 && (
        <div
          className={compact ? "grid" : "grid cols-4"}
          style={{ marginTop: 12, gap: 10 }}
        >
          {facts.map((f: any) => (
            <div
              key={f.label}
              style={{
                background: "var(--panel-soft)",
                border: "1px solid var(--line)",
                borderRadius: 10,
                padding: "8px 11px",
              }}
            >
              <div className="small muted">{f.label}</div>
              <div style={{ fontWeight: 600, fontSize: 13, marginTop: 2 }}>{f.value}</div>
            </div>
          ))}
        </div>
      )}

      {cols.length > 0 && rows.length > 0 && (
        <div className="scroll" style={{ marginTop: 14, maxHeight: compact ? 240 : 440 }}>
          <table>
            <thead>
              <tr>
                {cols.map((c: any) => (
                  <th key={c.key}>{c.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(compact ? rows.slice(0, 8) : rows).map((r: any, idx: number) => (
                <tr key={`${idx}-${r.pert_id || r.gene || idx}`}>
                  {cols.map((c: any) => {
                    const val = r[c.key];
                    if (c.key === "compound" && r.pert_id) {
                      return (
                        <td key={c.key}>
                          <Link href={`/compound/?id=${encodeURIComponent(r.pert_id)}`}>
                            {val}
                          </Link>
                          {!compact && r.pert_id && (
                            <div className="small muted mono">{r.pert_id}</div>
                          )}
                        </td>
                      );
                    }
                    if (c.key === "tdiki") return <td key={c.key}>{dikiBadge(val)}</td>;
                    if (c.key === "diril") return <td key={c.key}>{dirilBadge(val)}</td>;
                    if (c.key === "direction") {
                      return (
                        <td key={c.key}>
                          <span className={`badge ${String(val).startsWith("Up") ? "red" : "blue"}`}>
                            {val}
                          </span>
                        </td>
                      );
                    }
                    if (c.key === "tanimoto" && val != null && !Number.isNaN(Number(val))) {
                      const pct = Math.max(0, Math.min(100, Math.round(Number(val) * 100)));
                      return (
                        <td key={c.key}>
                          <div className="tanimoto-wrap">
                            <span className="mono">{val}</span>
                            <div className="tanimoto-bar">
                              <div className="tanimoto-fill" style={{ width: `${pct}%` }} />
                            </div>
                          </div>
                        </td>
                      );
                    }
                    return (
                      <td key={c.key} className={c.key === "rank" ? "mono muted" : ""}>
                        {val ?? "—"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {suggestions.length > 0 && onRunSuggestion && (
        <div className="chip-row" style={{ marginTop: 12 }}>
          <span className="small muted">Try:</span>
          {suggestions.map((s: string) => (
            <button
              key={s}
              type="button"
              className="chip"
              onClick={() => onRunSuggestion(s)}
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <div className="row" style={{ marginTop: 12, gap: 8 }}>
        {links.map((lk: any) => (
          <Link key={lk.href} href={lk.href}>
            <button type="button" className="ghost mini">
              {lk.label} →
            </button>
          </Link>
        ))}
        <span className="spacer" />
        {result.job_id && (
          <span className="small muted mono">job {result.job_id}</span>
        )}
      </div>

      <div className="small muted" style={{ marginTop: 10, borderTop: "1px solid var(--line)", paddingTop: 8 }}>
        Deterministic: every score, count, and safety flag comes directly from the NephroPerturb scoring engine; no LLM reasoning.
      </div>
    </div>
  );
}
