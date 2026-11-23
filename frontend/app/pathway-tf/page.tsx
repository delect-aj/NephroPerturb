"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { DikiBadge } from "@/components/Badges";
import { useAgent } from "@/components/AgentContext";
import { apiJson } from "@/lib/api";
import { PATHWAY_PRESETS } from "@/lib/examples";

export default function PathwayTF() {
  const { fill } = useAgent();
  const [rows, setRows] = useState<{ name: string; dir: number }[]>(PATHWAY_PRESETS[0].rows);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const raw = new URLSearchParams(window.location.search).get("targets");
    if (!raw) return;
    const parsed = raw
      .split(",")
      .map((pair) => {
        const [name, d] = pair.split(":");
        return name ? { name: name.trim(), dir: Number(d) < 0 ? -1 : 1 } : null;
      })
      .filter(Boolean) as { name: string; dir: number }[];
    if (parsed.length) setRows(parsed);
  }, []);

  async function run(customRows?: { name: string; dir: number }[]) {
    const useRows = customRows || rows;
    setLoading(true);
    setError("");
    try {
      const targets: Record<string, number> = {};
      useRows.forEach((r) => {
        if (r.name.trim()) targets[r.name.trim()] = r.dir;
      });
      const body = await apiJson("/api/v1/query/pathway-tf", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ targets, top_k: 30 }),
      });
      setData(body);
    } catch (e: any) {
      setError(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>Pathway & TF Search</h1>
      </div>
      <div className="sub">
        Query precomputed drug-induced functional activity matrices across PROGENy pathways, CollecTRI TFs, and curated renal pathology modules.
      </div>

      <div className="chip-row" style={{ marginBottom: 14 }}>
        <span className="small muted">Presets:</span>
        {PATHWAY_PRESETS.map((p) => (
          <button
            key={p.id}
            type="button"
            className="chip"
            onClick={() => {
              setRows(p.rows);
              run(p.rows);
            }}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="card">
        <h2>Target Regulatory Combination</h2>
        {rows.map((row, i) => (
          <div className="row" key={i} style={{ marginBottom: 8 }}>
            <input
              type="text"
              style={{ flex: 1, minWidth: 200 }}
              value={row.name}
              placeholder="Pathway, TF, or renal module (e.g., TGFb, SMAD3, NFkB)"
              onChange={(e) =>
                setRows(rows.map((r, j) => (j === i ? { ...r, name: e.target.value } : r)))
              }
            />
            <select
              value={row.dir}
              style={{ width: 150 }}
              onChange={(e) =>
                setRows(rows.map((r, j) => (j === i ? { ...r, dir: Number(e.target.value) } : r)))
              }
            >
              <option value={1}>Activate (+1)</option>
              <option value={-1}>Inhibit (−1)</option>
            </select>
            <button
              type="button"
              className="ghost"
              onClick={() => setRows(rows.filter((_, j) => j !== i))}
            >
              Remove
            </button>
          </div>
        ))}
        <div className="row" style={{ marginTop: 10 }}>
          <button
            type="button"
            className="ghost"
            onClick={() => setRows([...rows, { name: "", dir: -1 }])}
          >
            Add target
          </button>
          <button type="button" onClick={() => run()} disabled={loading}>
            {loading && <span className="spinner" />}
            {loading ? "Searching..." : "Search candidates"}
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => {
              const parts = rows
                .filter((r) => r.name.trim())
                .map((r) => `${r.dir < 0 ? "Inhibit" : "Activate"} ${r.name.trim()}`);
              if (parts.length) fill(parts.join(", "));
            }}
          >
            Ask Agent
          </button>
        </div>

        <div className="small muted" style={{ marginTop: 12, lineHeight: 1.6 }}>
          <strong>Valid identifiers:</strong> PROGENy (<span className="mono">TGFb, NFkB, JAK-STAT, Hypoxia, MAPK, EGFR, PI3K, TNFa, VEGF, WNT, p53</span>) · CollecTRI TFs (<span className="mono">SMAD3, SMAD4, PPARA, PPARG, STAT1, NFKB1, RELA, HIF1A</span>) · Renal modules (<span className="mono">PT_FAO_mito, Podocyte_slit, ECM_fibrosis, Complement, Ferroptosis_pyroptosis, ER_stress_UPR, RAAS, Tubular_injury_KIM1, Inflammation_NFkB, TGFb_SMAD, Apoptosis_p53, Autophagy</span>)
        </div>

        {error && (
          <div className="small" style={{ color: "var(--bad)", marginTop: 8 }}>
            {error}
          </div>
        )}
      </div>

      {data && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="row">
            <h2 style={{ margin: 0 }}>Candidate Drugs ({data.results?.length || 0})</h2>
            <span className="spacer" />
            <span className="small muted">
              Matched {data.used?.length || 0} · Unrecognized {(data.missing || []).join(", ") || "None"}
            </span>
          </div>
          <div className="scroll" style={{ marginTop: 10 }}>
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Compound</th>
                  <th>Pathway / TF Score</th>
                  <th>Phase</th>
                  <th>T-DIKI</th>
                </tr>
              </thead>
              <tbody>
                {(data.results || []).map((r: any, i: number) => (
                  <tr key={r.pert_id}>
                    <td className="mono muted">{i + 1}</td>
                    <td>
                      <Link
                        href={`/compound/?id=${encodeURIComponent(r.pert_id)}`}
                        prefetch={false}
                      >
                        {r.pert_iname || r.pert_id}
                      </Link>
                      <div className="small muted mono">{r.pert_id}</div>
                    </td>
                    <td className="mono">{Number(r.pathway_tf_score).toFixed(2)}</td>
                    <td className="small">{r.clinical_phase || "—"}</td>
                    <td><DikiBadge tier={r.tdiki_tier} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
