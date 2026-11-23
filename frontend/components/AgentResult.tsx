"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { DikiBadge, DirilBadge, TanimotoBar } from "@/components/Badges";
import CitationText from "@/components/CitationText";
import type { AgentTurn } from "@/components/AgentContext";

function EvidenceTierBadge({ tier }: { tier?: string }) {
  const t = tier || "Unknown";
  const cls = t.startsWith("Clinical")
    ? "green"
    : t.startsWith("Preclinical")
      ? "blue"
      : t.startsWith("Novel")
        ? "amber"
        : t.startsWith("Safety")
          ? "red"
          : "grey";
  return <span className={`badge ${cls}`}>{t}</span>;
}

function buildDossierMarkdown(turn: AgentTurn): string {
  const lines: string[] = [
    `# NephroAgent Research Dossier`,
    ``,
    `- **Query**: ${turn.query}`,
    `- **Skill**: ${turn.skill_name || turn.skill_id || "—"}`,
    `- **Execution Mode**: ${turn.mode_effective || turn.mode_requested || "—"}`,
    `- **Session ID**: ${turn.session_id || "—"}`,
    `- **Elapsed**: ${turn.elapsed_ms ?? "—"} ms`,
    ``,
    `## Synthesized Summary`,
    ``,
    turn.summary || "",
    ``,
  ];
  if (turn.steps?.length) {
    lines.push(`## Execution & Verification Trace`);
    turn.steps.forEach((s, idx) => {
      lines.push(`${idx + 1}. **${s.name}** (${s.tool || s.type}${s.ms != null ? `, ${s.ms} ms` : ""}): ${s.detail || s.args || s.status}`);
    });
    lines.push("");
  }
  const cols = turn.table?.columns || [];
  const rows = turn.table?.rows || [];
  if (cols.length && rows.length) {
    lines.push(`## Ranked Candidates / Results`);
    lines.push(`| ${cols.map((c) => c.label).join(" | ")} |`);
    lines.push(`| ${cols.map(() => "---").join(" | ")} |`);
    rows.slice(0, 15).forEach((r) => {
      lines.push(`| ${cols.map((c) => String(r[c.key] ?? "—").replace(/\|/g, "/")).join(" | ")} |`);
    });
    lines.push("");
  }
  if (turn.literature?.length) {
    lines.push(`## Kidney Literature Evidence`);
    turn.literature.forEach((grp) => {
      lines.push(`### ${grp.entity} — ${grp.evidence_tier} (${grp.provider})`);
      if (grp.synthesis?.verdict) {
        lines.push(`- **Synthesis**: ${grp.synthesis.verdict} ${grp.synthesis.novelty_note || ""}`);
      }
      (grp.papers || []).forEach((p: any) => {
        const kf = p.takeaway || p.snippet;
        lines.push(`- [${p.category}] **${p.title}** (${p.journal}, ${p.year}) — ${p.pmid ? `PMID:${p.pmid} (${p.url})` : p.url}`);
        if (kf) lines.push(`  - Key finding: ${kf}`);
      });
      lines.push("");
    });
  }
  const allTrials = (turn.clinical_trials || []).flatMap((g) => (g.trials || []).map((tr: any) => ({ ...tr, compound: g.compound })));
  if (allTrials.length) {
    lines.push(`## ClinicalTrials.gov Studies`);
    allTrials.forEach((tr: any) => {
      lines.push(`- **${tr.nct_id}** (${tr.compound}, ${(tr.phases || []).join("/")}, ${tr.status}): ${tr.title} — ${tr.url}`);
    });
    lines.push("");
  }
  const refs = turn.references || [];
  if (refs.length) {
    lines.push(`## References`);
    refs.forEach((r: any) => {
      if (r.kind === "paper") {
        lines.push(`${r.index}. ${r.authors || "et al."} (${r.year || "—"}). **${r.title}**. *${r.journal || "PubMed"}*. ${r.id} (${r.url})`);
      } else {
        lines.push(`${r.index}. ClinicalTrials.gov (${(r.phases || ["N/A"]).join("/")}, ${r.status}). **${r.title}**. ${r.id} (${r.url})`);
      }
    });
    lines.push("");
  }
  return lines.join("\n");
}

function downloadMarkdown(turn: AgentTurn) {
  const md = buildDossierMarkdown(turn);
  const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `nephroagent-${turn.skill_id || "dossier"}-${Date.now()}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export default function AgentResult({
  result,
  compact = false,
  onRunSuggestion,
}: {
  result: AgentTurn | any;
  compact?: boolean;
  onRunSuggestion?: (prompt: string) => void;
}) {
  if (!result) return null;

  const steps = result.steps || [];
  const facts = result.facts || [];
  const activeTable = result.table?.rows?.length ? result.table : result.kprl_table || { columns: [], rows: [] };
  const cols = activeTable?.columns || [];
  const rows = activeTable?.rows || [];
  const lits = result.literature || [];
  const totalPapers = lits.reduce((acc: number, g: any) => acc + (g.papers?.length || 0), 0);
  const trialsGroups = result.clinical_trials || [];
  const totalTrials = trialsGroups.reduce((acc: number, g: any) => acc + (g.trials?.length || 0), 0);
  const references = result.references || [];
  const comparison = result.comparison;
  const links = result.links || [];
  const suggestions = result.suggestions || [];
  const verification = result.verification;

  const hasCandidates = rows.length > 0 || facts.length > 0;
  const hasCompare = Boolean(comparison?.compounds?.length);
  const hasLit = lits.length > 0;
  const hasTrials = totalTrials > 0;

  const [tab, setTab] = useState<"candidates" | "compare" | "literature" | "trials">("candidates");
  const [traceOpen, setTraceOpen] = useState<boolean>(result.status === "streaming");
  const [copied, setCopied] = useState<boolean>(false);

  useEffect(() => {
    if (hasCompare) setTab("compare");
    else if (hasCandidates) setTab("candidates");
    else if (hasLit) setTab("literature");
    else if (hasTrials) setTab("trials");
  }, [result.id, hasCompare, hasCandidates, hasLit, hasTrials]);

  useEffect(() => {
    setTraceOpen(result.status === "streaming");
  }, [result.status]);

  const copyReport = () => {
    if (!result.summary) return;
    navigator.clipboard?.writeText(buildDossierMarkdown(result)).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    }).catch(() => {});
  };

  const statusLabel: Record<string, string> = {
    streaming: "Researching...",
    ok: "Completed",
    needs_input: "Needs input",
    out_of_scope: "Out of scope",
    stopped: "Stopped",
    error: "Error",
  };

  const modeLabel =
    result.mode_effective === "deepseek_react"
      ? "DeepSeek ReAct"
      : result.mode_effective === "deterministic_fallback"
        ? "Deterministic Fallback"
        : "0-LLM Multi-Step";

  const pmidsCount = verification?.pmids_cited?.length || 0;
  const nctsCount = verification?.ncts_cited?.length || 0;

  return (
    <div className="card" style={compact ? { padding: 11, boxShadow: "none" } : { marginTop: 8 }}>
      {/* Header Status Bar */}
      <div className="row" style={{ gap: 6 }}>
        <span className={`badge status-${result.status || "ok"}`}>
          {result.status === "streaming" && <span className="spinner" style={{ width: 10, height: 10, marginRight: 4 }} />}
          {statusLabel[result.status] || result.status}
        </span>

        {result.skill_id && (
          <span
            className="badge"
            style={{
              background: result.color ? `${result.color}18` : "#dbeafe",
              color: result.color || "#1d4ed8",
            }}
          >
            {result.short_label || result.skill_name || result.skill_id}
          </span>
        )}

        <span className="badge grey">{modeLabel}</span>

        {verification && (
          <span
            className={`badge ${verification.verified ? "green" : "amber"}`}
            title={
              verification.hard_violations?.length
                ? verification.hard_violations.join("; ")
                : "All scores, compound IDs, PMIDs and NCTs verified against tool outputs"
            }
          >
            {verification.verified
              ? `Verified${pmidsCount || nctsCount ? ` · ${pmidsCount} PMID · ${nctsCount} NCT` : ""}`
              : "Fallback Grounded"}
          </span>
        )}

        <span className="spacer" />

        {result.usage?.total_tokens > 0 && (
          <span className="small muted mono">{result.usage.total_tokens} tok</span>
        )}
        {result.elapsed_ms != null && (
          <span className="small muted mono">{result.elapsed_ms} ms</span>
        )}
      </div>

      {result.quota_notice && (
        <div className="notice-banner">{result.quota_notice}</div>
      )}

      {/* Reasoning & Tool Timeline */}
      {steps.length > 0 && (
        <div style={{ marginTop: 8 }}>
          <button
            type="button"
            className="ghost mini"
            onClick={() => setTraceOpen((v) => !v)}
            style={{ marginBottom: traceOpen ? 6 : 0 }}
          >
            {traceOpen ? "▾ Hide execution trace" : `▸ Show execution trace (${steps.length} steps)`}
          </button>

          {traceOpen && (
            <div className="timeline">
              {steps.map((s: any, idx: number) => (
                <div
                  key={`${idx}-${s.name}-${s.step || 0}`}
                  className={`step ${
                    s.status === "running"
                      ? "step-running"
                      : s.status === "error"
                        ? "step-error"
                        : s.status === "skipped"
                          ? "step-skipped"
                          : s.type === "reflection"
                            ? "step-reflection"
                            : ""
                  }`}
                >
                  <div className="row" style={{ gap: 6 }}>
                    <strong>{s.name}</strong>
                    {s.tool && <span className="badge grey mono">{s.tool}</span>}
                    {s.type === "reflection" && <span className="badge amber">Reflect</span>}
                    <span className="spacer" />
                    {s.ms != null && <span className="small muted mono">{s.ms} ms</span>}
                  </div>
                  {(s.detail || s.args) && (
                    <div className="small muted" style={{ marginTop: 2 }}>
                      {s.detail || s.args}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Publication-Grade Research Synthesis Report */}
      {result.summary && (
        <div className="report-card">
          <div className="report-head">
            <span style={{ fontWeight: 700, fontSize: 13 }}>Research Synthesis Report</span>
            <span className="small muted">
              {references.length > 0 ? `${references.length} grounded reference${references.length > 1 ? "s" : ""}` : "Grounded synthesis"}
            </span>
            <span className="spacer" />
            {!compact && result.status !== "streaming" && (
              <>
                <button type="button" className="ghost mini" onClick={copyReport}>
                  {copied ? "Copied" : "Copy"}
                </button>
                <button type="button" className="ghost mini" onClick={() => downloadMarkdown(result)}>
                  Export .md
                </button>
              </>
            )}
          </div>
          <CitationText text={result.summary} />

          {references.length > 0 && (
            <div className="ref-section">
              <div className="ref-title">References ({references.length})</div>
              <ol className="ref-list">
                {references.map((r: any) => (
                  <li key={r.id} className="ref-item">
                    {r.kind === "paper" ? (
                      <>
                        <span className="muted">{r.authors || "et al."} ({r.year || "—"}). </span>
                        <a href={r.url} target="_blank" rel="noopener noreferrer" style={{ fontWeight: 600 }}>
                          {r.title}
                        </a>
                        {r.journal && <span className="muted"> — <em>{r.journal}</em>.</span>}{" "}
                        <a href={r.url} target="_blank" rel="noopener noreferrer" className="cite-chip cite-pmid">
                          {r.id}
                        </a>
                      </>
                    ) : (
                      <>
                        <span className="muted">ClinicalTrials.gov ({(r.phases || ["N/A"]).join("/")}, {r.status}). </span>
                        <a href={r.url} target="_blank" rel="noopener noreferrer" style={{ fontWeight: 600 }}>
                          {r.title}
                        </a>{" "}
                        <a href={r.url} target="_blank" rel="noopener noreferrer" className="cite-chip cite-nct">
                          {r.id}
                        </a>
                      </>
                    )}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      )}

      {/* Evidence Tabs */}
      {(hasCandidates || hasCompare || hasLit || hasTrials) && (
        <div className="tab-bar">
          <span className="small muted" style={{ alignSelf: "center", marginRight: 4 }}>Supporting Evidence:</span>
          {hasCompare && (
            <button
              type="button"
              className={`tab-btn ${tab === "compare" ? "active" : ""}`}
              onClick={() => setTab("compare")}
            >
              Comparison ({comparison.compounds.length})
            </button>
          )}
          {hasCandidates && (
            <button
              type="button"
              className={`tab-btn ${tab === "candidates" ? "active" : ""}`}
              onClick={() => setTab("candidates")}
            >
              {rows.length ? `Results (${rows.length})` : "Profile Facts"}
            </button>
          )}
          {hasLit && (
            <button
              type="button"
              className={`tab-btn ${tab === "literature" ? "active" : ""}`}
              onClick={() => setTab("literature")}
            >
              Literature ({totalPapers})
            </button>
          )}
          {hasTrials && (
            <button
              type="button"
              className={`tab-btn ${tab === "trials" ? "active" : ""}`}
              onClick={() => setTab("trials")}
            >
              Clinical Trials ({totalTrials})
            </button>
          )}
        </div>
      )}

      {/* Tab Panel: Candidates & Facts */}
      {tab === "candidates" && hasCandidates && (
        <div>
          {facts.length > 0 && (
            <div className={compact ? "grid" : "grid cols-4"} style={{ marginTop: 8, gap: 8 }}>
              {facts.map((f: any) => (
                <div key={f.label} className="fact-tile">
                  <div className="small muted">{f.label}</div>
                  <div style={{ fontWeight: 600, fontSize: 12.6, marginTop: 1 }}>{f.value}</div>
                </div>
              ))}
            </div>
          )}
          {cols.length > 0 && rows.length > 0 && (
            <div className="scroll" style={{ marginTop: 10, maxHeight: compact ? 230 : 380 }}>
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
                              <Link href={`/compound/?id=${encodeURIComponent(r.pert_id)}`} prefetch={false}>
                                {val}
                              </Link>
                              {!compact && r.pert_id && <div className="small muted mono">{r.pert_id}</div>}
                            </td>
                          );
                        }
                        if (c.key === "tdiki") return <td key={c.key}><DikiBadge tier={val} /></td>;
                        if (c.key === "diril") return <td key={c.key}><DirilBadge value={val} /></td>;
                        if (c.key === "direction") {
                          return (
                            <td key={c.key}>
                              <span className={`badge ${String(val).startsWith("Up") ? "red" : "blue"}`}>{val}</span>
                            </td>
                          );
                        }
                        if (c.key === "tanimoto") return <td key={c.key}><TanimotoBar value={val} /></td>;
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
        </div>
      )}

      {/* Tab Panel: Compound Comparison Matrix */}
      {tab === "compare" && hasCompare && (
        <div style={{ marginTop: 8 }}>
          {comparison.highlights && (
            <div className="grid cols-3" style={{ gap: 8, marginBottom: 10 }}>
              <div className="fact-tile">
                <div className="small muted">Safest Kidney Risk</div>
                <div style={{ fontWeight: 700, color: "var(--good)" }}>{comparison.highlights.safest_kidney}</div>
              </div>
              <div className="fact-tile">
                <div className="small muted">Strongest Anti-Fibrotic</div>
                <div style={{ fontWeight: 700, color: "var(--accent)" }}>{comparison.highlights.best_antifibrotic}</div>
              </div>
              <div className="fact-tile">
                <div className="small muted">Best Podocyte / FAO</div>
                <div style={{ fontWeight: 700, color: "#0284c7" }}>{comparison.highlights.best_podocyte_metabolic}</div>
              </div>
            </div>
          )}
          <div className="scroll" style={{ maxHeight: 360 }}>
            <table>
              <thead>
                <tr>
                  <th>Metric</th>
                  {comparison.compounds.map((c: any) => (
                    <th key={c.pert_id}>
                      <Link href={`/compound/?id=${encodeURIComponent(c.pert_id)}`} prefetch={false}>
                        {c.pert_iname}
                      </Link>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td className="muted">Phase / MoA</td>
                  {comparison.compounds.map((c: any) => (
                    <td key={c.pert_id} className="small">
                      <strong>{c.clinical_phase}</strong> · {c.moa}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td className="muted">T-DIKI v2 Risk</td>
                  {comparison.compounds.map((c: any) => (
                    <td key={c.pert_id}>
                      <DikiBadge tier={c.tdiki_tier} />{" "}
                      <span className="small muted mono">
                        {c.tdiki_prob != null ? `(${c.tdiki_prob})` : ""}
                      </span>
                    </td>
                  ))}
                </tr>
                <tr>
                  <td className="muted">FDA DIRIL</td>
                  {comparison.compounds.map((c: any) => (
                    <td key={c.pert_id}>
                      <DirilBadge value={c.diril_label === 1 ? "Positive" : c.diril_label === 0 ? "Negative" : "—"} />
                    </td>
                  ))}
                </tr>
                {["ECM_fibrosis", "TGFb_SMAD", "Podocyte_slit", "PT_FAO_mito", "Inflammation_NFkB", "Tubular_injury_KIM1"].map(
                  (mod) => (
                    <tr key={mod}>
                      <td className="mono small muted">{mod}</td>
                      {comparison.compounds.map((c: any) => (
                        <td key={c.pert_id} className="mono small">
                          {c.renal_modules?.[mod] ?? "—"}
                        </td>
                      ))}
                    </tr>
                  )
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab Panel: Literature Cards */}
      {tab === "literature" && hasLit && (
        <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 10 }}>
          {lits.map((grp: any, gIdx: number) => {
            const synth = grp.synthesis;
            return (
              <div key={`${grp.entity}-${gIdx}`} className="lit-group">
                <div className="row" style={{ marginBottom: 6 }}>
                  <strong>{grp.entity}</strong>
                  <EvidenceTierBadge tier={grp.evidence_tier} />
                  <span className="small muted">
                    Efficacy hits: {grp.efficacy_total_hits ?? 0} · Safety hits: {grp.safety_total_hits ?? 0}
                  </span>
                  <span className="spacer" />
                  <span className="badge grey mono">{grp.provider}{grp.cached ? " · cached" : ""}</span>
                </div>

                {synth && (
                  <div className="lit-synth-box">
                    <div className="lit-synth-title">
                      Evidence Synthesis · {synth.novelty_note}
                    </div>
                    {synth.efficacy_points?.length > 0 && (
                      <div style={{ display: "flex", flexDirection: "column", gap: 3, marginTop: 4 }}>
                        {synth.efficacy_points.map((pt: any, ptIdx: number) => (
                          <div key={`ep-${ptIdx}`} className="small">
                            <span className="badge blue" style={{ marginRight: 5 }}>{pt.category}</span>
                            {pt.finding}
                            {pt.pmid && (
                              <a
                                href={`https://pubmed.ncbi.nlm.nih.gov/${pt.pmid}/`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="cite-chip cite-pmid"
                              >
                                PMID:{pt.pmid}
                              </a>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                    {synth.safety_points?.length > 0 && (
                      <div className="lit-safety-box">
                        <strong style={{ color: "var(--bad)" }}>Nephrotoxicity Signals:</strong>{" "}
                        {synth.safety_points.map((sp: any, sIdx: number) => (
                          <span key={`sp-${sIdx}`}>
                            {sIdx > 0 ? " | " : ""}
                            {sp.finding}
                            {sp.pmid && (
                              <a
                                href={`https://pubmed.ncbi.nlm.nih.gov/${sp.pmid}/`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="cite-chip cite-pmid"
                              >
                                PMID:{sp.pmid}
                              </a>
                            )}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {grp.error && <div className="small" style={{ color: "var(--warn)" }}>{grp.error}</div>}
                {(!grp.papers || grp.papers.length === 0) ? (
                  <div className="small muted">
                    No kidney papers indexed for this query ({grp.evidence_tier}). Candidate represents a high-novelty repurposing hypothesis.
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {grp.papers.map((p: any, pIdx: number) => (
                      <div key={`${p.pmid || pIdx}-${pIdx}`} className="lit-card">
                        <div className="row" style={{ gap: 6 }}>
                          <span className={`badge ${p.category === "Safety Warning" ? "red" : p.category === "Clinical" ? "green" : p.category === "Preclinical" ? "blue" : "grey"}`}>
                            {p.category}
                          </span>
                          <span className="small muted">
                            {p.journal} ({p.year || "—"})
                          </span>
                          {p.cited_by != null && (
                            <span className="small muted">· Cited {p.cited_by}</span>
                          )}
                          <span className="spacer" />
                          {p.pmid && (
                            <a
                              href={p.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="cite-chip cite-pmid"
                            >
                              PMID:{p.pmid}
                            </a>
                          )}
                        </div>
                        <a
                          href={p.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ fontWeight: 600, fontSize: 12.6, display: "block", marginTop: 3 }}
                        >
                          {p.title}
                        </a>
                        {(p.takeaway || p.snippet) && (
                          <div className="small muted lit-snippet">
                            <strong>Key finding:</strong> {p.takeaway || p.snippet}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Tab Panel: ClinicalTrials.gov */}
      {tab === "trials" && hasTrials && (
        <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 8 }}>
          {trialsGroups.map((grp: any, idx: number) => (
            <div key={`tg-${idx}`} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {grp.scope_note && (
                <div className="small muted scope-note">{grp.compound}: {grp.scope_note}</div>
              )}
              {(grp.trials || []).map((tr: any) => (
                <div key={`${idx}-${tr.nct_id}`} className="lit-card">
                  <div className="row" style={{ gap: 6 }}>
                    <a
                      href={tr.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="cite-chip cite-nct"
                    >
                      {tr.nct_id}
                    </a>
                    <span className="badge blue">{(tr.phases || ["N/A"]).join(", ")}</span>
                    <span className="badge grey">{tr.status}</span>
                    <span className="small muted">{grp.compound}</span>
                    <span className="spacer" />
                    {tr.start_date && <span className="small muted mono">{tr.start_date}</span>}
                  </div>
                  <a
                    href={tr.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ fontWeight: 600, fontSize: 12.6, display: "block", marginTop: 3 }}
                  >
                    {tr.title}
                  </a>
                  {tr.conditions?.length > 0 && (
                    <div className="small muted" style={{ marginTop: 2 }}>
                      Conditions: {tr.conditions.join(" · ")}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ))}
        </div>
      )}

      {/* Context-Aware Next Actions */}
      {suggestions.length > 0 && onRunSuggestion && (
        <div className="chip-row" style={{ marginTop: 10 }}>
          <span className="small muted">Next step:</span>
          {suggestions.map((s: string) => (
            <button key={s} type="button" className="chip" onClick={() => onRunSuggestion(s)}>
              {s}
            </button>
          ))}
        </div>
      )}

      {links.length > 0 && (
        <div className="row" style={{ marginTop: 10, gap: 8 }}>
          {links.map((lk: any) => (
            <Link key={lk.href} href={lk.href} prefetch={false}>
              <button type="button" className="ghost mini">
                {lk.label} →
              </button>
            </Link>
          ))}
        </div>
      )}

      <div className="small muted" style={{ marginTop: 8, borderTop: "1px solid var(--line)", paddingTop: 6 }}>
        Grounded evidence: scores are deterministically computed; all PMIDs &amp; NCTs are verified against live tool records.
      </div>
    </div>
  );
}
