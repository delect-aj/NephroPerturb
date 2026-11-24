"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { RadarChart } from "@/components/Chart";
import { DikiBadge, DirilBadge } from "@/components/Badges";
import { useAgent } from "@/components/AgentContext";
import { apiJson } from "@/lib/api";
import { SIGNATURE_PRESETS } from "@/lib/examples";

const COMPARTMENTS: [string, string][] = [
  ["whole_kidney", "Whole kidney"],
  ["glomerulus", "Glomerulus"],
  ["podocyte", "Podocyte"],
  ["pt", "Proximal tubule (PT)"],
  ["tal", "Thick ascending limb (TAL)"],
  ["dct", "Distal convoluted tubule (DCT)"],
  ["cd", "Collecting duct (CD)"],
  ["endo", "Endothelium"],
  ["immune", "Immune"],
  ["tubule", "Tubule"],
];

export default function Workbench() {
  const { fill } = useAgent();
  const [activePreset, setActivePreset] = useState(SIGNATURE_PRESETS[0].id);
  const [up, setUp] = useState(SIGNATURE_PRESETS[0].up);
  const [down, setDown] = useState(SIGNATURE_PRESETS[0].down);
  const [context, setContext] = useState("kprl");
  const [tier, setTier] = useState("all");
  const [compartment, setCompartment] = useState("whole_kidney");
  const [approvedOnly, setApprovedOnly] = useState(false);
  const [collapse, setCollapse] = useState(true);
  const [maxDiki, setMaxDiki] = useState("");
  const [w1, setW1] = useState(1.0);
  const [w2, setW2] = useState(0.5);
  const [w3, setW3] = useState(0.2);
  const [w4, setW4] = useState(0.2);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<any>(null);
  const [selected, setSelected] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const upQ = sp.get("up");
    const dnQ = sp.get("down");
    const ctxQ = sp.get("context");
    if (upQ) setUp(upQ.split(",").map((s) => s.trim()).filter(Boolean).join("\n"));
    if (dnQ) setDown(dnQ.split(",").map((s) => s.trim()).filter(Boolean).join("\n"));
    if (ctxQ) setContext(ctxQ);
  }, []);

  const parseGenes = (s: string) =>
    s.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean);

  async function run() {
    setLoading(true);
    setError("");
    setSelected(null);
    try {
      const payload = await apiJson(
        "/api/v1/query/signature",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            up_genes: parseGenes(up),
            down_genes: parseGenes(down),
            context,
            gene_tier: tier,
            kidney_compartment: compartment,
            weights: { w1, w2, w3, w4 },
            filters: {
              approved_only: approvedOnly,
              collapse_scaffold: collapse,
              ...(maxDiki ? { max_diki_tier: maxDiki } : {}),
            },
            top_k: 50,
          }),
        },
        45000
      );
      setData(payload);
      setSelected(payload.results?.[0] || null);
    } catch (err: any) {
      setError(String(err.message || err));
    } finally {
      setLoading(false);
    }
  }

  function exportJson() {
    if (!data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `nephroperturb_${data.job_id || "result"}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const radarItems = useMemo(() => {
    if (!selected) return [];
    return [
      { label: "XSum", value: Math.abs(Number(selected.tau_xsum || 0)) },
      { label: "Zhang", value: Math.abs(Number(selected.tau_zhang || 0)) },
      { label: "WTCS", value: Math.abs(Number(selected.tau_wtcs || 0)) },
      { label: "Func", value: Math.abs(Number(selected.tau_func || 0)) },
    ];
  }, [selected]);

  return (
    <>
      <div className="page-head">
        <h1>Signature Workbench</h1>
      </div>
      <div className="sub">
        Rank 21,299 compounds by multi-scale signature reversal and NephroSafe toxicity guardrails.
      </div>

      <div className="chip-row" style={{ marginBottom: 10 }}>
        <span className="small muted">Presets:</span>
        {SIGNATURE_PRESETS.map((p) => (
          <button
            key={p.id}
            type="button"
            className={`chip ${activePreset === p.id ? "active" : ""}`}
            onClick={() => {
              setActivePreset(p.id);
              setUp(p.up);
              setDown(p.down);
              setContext(p.context);
              setCompartment(p.compartment);
              setData(null);
              setSelected(null);
              setError("");
            }}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>Disease Signature</h2>
          <label>Up-regulated genes (newline or comma separated)</label>
          <textarea value={up} onChange={(e) => setUp(e.target.value)} />
          <label>Down-regulated genes</label>
          <textarea value={down} onChange={(e) => setDown(e.target.value)} />
          <div className="row" style={{ marginTop: 10 }}>
            <button type="button" onClick={run} disabled={loading}>
              {loading && <span className="spinner" />}
              {loading ? "Scoring..." : "Run reversal query"}
            </button>
            <button
              type="button"
              className="ghost"
              onClick={() => {
                const u = parseGenes(up).join(" ");
                const d = parseGenes(down).join(" ");
                fill(`Up: ${u}; Down: ${d}`, "disease-repurposing");
              }}
            >
              Send to Agent
            </button>
            {data && (
              <button type="button" className="ghost" onClick={exportJson}>
                Export JSON
              </button>
            )}
          </div>
          {error && (
            <div className="small" style={{ color: "var(--bad)", marginTop: 8 }}>
              {error}
            </div>
          )}
        </div>

        <div className="card">
          <h2>Scoring Parameters &amp; Weights</h2>
          <div className="grid cols-2">
            <div>
              <label>Perturbation context</label>
              <select value={context} onChange={(e) => setContext(e.target.value)}>
                <option value="kprl">K-PRL (Kidney Consensus Signature)</option>
                <option value="pan">Pan-cell consensus (systemic)</option>
                <option value="renal_epi">HA1E renal epithelium (tubular/fibrosis)</option>
                <option value="renal_endo">Endothelium (glomerular/vascular)</option>
                <option value="renal_immune">Immune (LN, IgAN)</option>
              </select>
            </div>
            <div>
              <label>Gene tier</label>
              <select value={tier} onChange={(e) => setTier(e.target.value)}>
                <option value="all">All 12,328 genes</option>
                <option value="bing">Best Inferred Genes (BING, 10,174)</option>
                <option value="lm">Landmark Genes Only (978)</option>
              </select>
            </div>
            <div>
              <label>Kidney compartment</label>
              <select value={compartment} onChange={(e) => setCompartment(e.target.value)}>
                {COMPARTMENTS.map(([val, lbl]) => (
                  <option key={val} value={val}>
                    {lbl}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label>Max Nephrotoxicity Risk (T-DIKI)</label>
              <select value={maxDiki} onChange={(e) => setMaxDiki(e.target.value)}>
                <option value="">No limit</option>
                <option value="Moderate">Up to Moderate</option>
                <option value="Low">Low only</option>
              </select>
            </div>
          </div>

          <div className="row" style={{ marginTop: 8 }}>
            <label style={{ margin: 0, display: "flex", alignItems: "center", gap: 5 }}>
              <input
                type="checkbox"
                checked={approvedOnly}
                onChange={(e) => setApprovedOnly(e.target.checked)}
              />
              Approved drugs only
            </label>
            <label style={{ margin: 0, display: "flex", alignItems: "center", gap: 5 }}>
              <input
                type="checkbox"
                checked={collapse}
                onChange={(e) => setCollapse(e.target.checked)}
              />
              Collapse by scaffold
            </label>
          </div>

          <div className="grid cols-2" style={{ marginTop: 8 }}>
            {[
              ["Efficacy (RenalConn)", w1, setW1],
              ["Nephrotoxicity penalty", w2, setW2],
              ["Compartment expression", w3, setW3],
              ["Genetic support", w4, setW4],
            ].map(([label, val, set]: any) => (
              <div key={label}>
                <label style={{ marginTop: 4 }}>
                  {label}: {Number(val).toFixed(2)}
                </label>
                <input
                  type="range"
                  min={0}
                  max={2}
                  step={0.05}
                  value={val}
                  onChange={(e) => set(Number(e.target.value))}
                  style={{ width: "100%" }}
                />
              </div>
            ))}
          </div>
        </div>
      </div>

      {data && (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="row">
            <h2 style={{ margin: 0 }}>Candidate Drugs ({data.results?.length || 0})</h2>
            <span className="spacer" />
            <span className="small muted mono">job {data.job_id}</span>
          </div>
          <div className="scroll" style={{ marginTop: 8 }}>
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Compound</th>
                  <th>Phase</th>
                  <th>RTPS</th>
                  <th>RenalConn</th>
                  <th>τ XSum</th>
                  <th>τ Zhang</th>
                  <th>τ WTCS</th>
                  <th>τ Func</th>
                  <th>T-DIKI</th>
                  <th>DIRIL</th>
                  <th>MoA</th>
                </tr>
              </thead>
              <tbody>
                {(data.results || []).map((r: any, i: number) => (
                  <tr
                    key={r.pert_id}
                    onClick={() => setSelected(r)}
                    style={{ cursor: "pointer" }}
                  >
                    <td className="mono muted">{i + 1}</td>
                    <td>
                      <Link
                        href={`/compound/?id=${encodeURIComponent(r.pert_id)}`}
                        prefetch={false}
                        onClick={(e) => e.stopPropagation()}
                      >
                        {r.pert_iname || r.pert_id}
                      </Link>
                      <div className="small muted mono">{r.pert_id}</div>
                    </td>
                    <td className="small">{r.clinical_phase || "—"}</td>
                    <td className="mono">{Number(r.rtps).toFixed(1)}</td>
                    <td className="mono">{Number(r.renalconn).toFixed(1)}</td>
                    {["xsum", "zhang", "wtcs", "func"].map((m) => (
                      <td key={m} className="mono">
                        {Number(r[`tau_${m}`] || 0).toFixed(0)}
                      </td>
                    ))}
                    <td><DikiBadge tier={r.tdiki_tier} /></td>
                    <td><DirilBadge value={r.diril_label} /></td>
                    <td className="small">{r.moa ? String(r.moa).split("|")[0] : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {selected && radarItems.length > 0 && (
        <div className="grid cols-2" style={{ marginTop: 12 }}>
          <div className="card">
            <h2>Reversal Score Components (τ) · {selected.pert_iname || selected.pert_id}</h2>
            <RadarChart items={radarItems} height={260} />
          </div>
          <div className="card">
            <h2>Query Provenance</h2>
            <div className="kv">
              <div>Input hash</div>
              <div className="mono small">{data.provenance?.input_hash?.slice(0, 32)}…</div>
              <div>Resolved genes</div>
              <div>
                Up {data.provenance?.n_up} / Down {data.provenance?.n_down}
              </div>
              <div>Matrix version</div>
              <div>{data.provenance?.matrix_version}</div>
              <div>Generated at</div>
              <div className="small">{data.provenance?.generated_at}</div>
              <div>Unrecognized genes</div>
              <div className="small">
                {[
                  ...(data.provenance?.missing_up || []),
                  ...(data.provenance?.missing_down || []),
                ].join(", ") || "None"}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
