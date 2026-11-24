"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { DikiBadge } from "@/components/Badges";
import { useAgent } from "@/components/AgentContext";
import { apiJson } from "@/lib/api";
import { PATHWAY_PRESETS } from "@/lib/examples";

const PROGENY_IDS = ["TGFb", "NFkB", "JAK-STAT", "Hypoxia", "MAPK", "EGFR", "PI3K", "TNFa", "VEGF", "WNT", "p53"];
const TF_IDS = ["SMAD3", "SMAD4", "PPARA", "PPARG", "STAT1", "STAT3", "HIF1A", "NFE2L2", "NR3C1", "WT1", "FOXO3"];
const MODULE_IDS = [
  "PT_FAO_mito",
  "Podocyte_slit",
  "ECM_fibrosis",
  "Complement",
  "Ferroptosis_pyroptosis",
  "ER_stress_UPR",
  "RAAS",
  "Tubular_injury_KIM1",
  "Inflammation_NFkB",
  "TGFb_SMAD",
  "Apoptosis_p53",
  "Autophagy",
];

export default function PathwayTF() {
  const { fill } = useAgent();
  const [rows, setRows] = useState<{ name: string; dir: number }[]>(
    () => PATHWAY_PRESETS[0].rows.map((r) => ({ ...r }))
  );
  const [activePreset, setActivePreset] = useState<string>(PATHWAY_PRESETS[0].id);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function run(customRows?: { name: string; dir: number }[], syncUrl = false) {
    const useRows = (customRows || rows).filter((r) => r.name.trim());
    if (!useRows.length) {
      setError("Please enter at least one pathway, TF, or renal module.");
      return;
    }
    setLoading(true);
    setError("");
    if (syncUrl) {
      const q = useRows.map((r) => `${r.name.trim()}:${r.dir}`).join(",");
      window.history.replaceState(null, "", `/pathway-tf/?targets=${encodeURIComponent(q)}`);
    }
    try {
      const targets: Record<string, number> = {};
      useRows.forEach((r) => {
        targets[r.name.trim()] = r.dir;
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

  useEffect(() => {
    const raw = new URLSearchParams(window.location.search).get("targets");
    if (raw) {
      const parsed = raw
        .split(",")
        .map((pair) => {
          const [name, d] = pair.split(":");
          return name ? { name: name.trim(), dir: Number(d) < 0 ? -1 : 1 } : null;
        })
        .filter(Boolean) as { name: string; dir: number }[];
      if (parsed.length) {
        setRows(parsed);
        setActivePreset("");
        run(parsed, false);
        return;
      }
    }
    run(PATHWAY_PRESETS[0].rows.map((r) => ({ ...r })), false);
  }, []);

  function addQuickTarget(id: string) {
    setActivePreset("");
    const exists = rows.some((r) => r.name.trim().toUpperCase() === id.toUpperCase());
    if (exists) return;
    const emptyIdx = rows.findIndex((r) => !r.name.trim());
    const next =
      emptyIdx >= 0
        ? rows.map((r, idx) => (idx === emptyIdx ? { ...r, name: id } : r))
        : [...rows, { name: id, dir: -1 }];
    setRows(next);
  }

  return (
    <>
      <div className="page-head">
        <h1>Pathway &amp; TF Search</h1>
      </div>
      <div className="sub">
        Screen compounds against precomputed PROGENy pathways, CollecTRI TFs, and curated renal modules.
      </div>

      <div className="chip-row" style={{ marginBottom: 10 }}>
        <span className="small muted">Presets:</span>
        {PATHWAY_PRESETS.map((p) => (
          <button
            key={p.id}
            type="button"
            className={`chip ${activePreset === p.id ? "active" : ""}`}
            onClick={() => {
              const cloned = p.rows.map((r) => ({ ...r }));
              setRows(cloned);
              setActivePreset(p.id);
              run(cloned, true);
            }}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="card">
        <h2>Target Regulatory Combination</h2>
        {rows.map((row, i) => (
          <div className="row" key={i} style={{ marginBottom: 6 }}>
            <input
              type="text"
              style={{ flex: 1, minWidth: 200 }}
              value={row.name}
              placeholder="Pathway, TF, or renal module (e.g. TGFb, SMAD3, NFkB)"
              onChange={(e) => {
                setActivePreset("");
                setRows(rows.map((r, j) => (j === i ? { ...r, name: e.target.value } : r)));
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  run(undefined, true);
                }
              }}
            />
            <select
              value={row.dir}
              style={{ width: 145 }}
              onChange={(e) => {
                setActivePreset("");
                setRows(rows.map((r, j) => (j === i ? { ...r, dir: Number(e.target.value) } : r)));
              }}
            >
              <option value={1}>Activate (+1)</option>
              <option value={-1}>Inhibit (−1)</option>
            </select>
            <button
              type="button"
              className="ghost mini"
              onClick={() => {
                setActivePreset("");
                setRows(rows.length > 1 ? rows.filter((_, j) => j !== i) : [{ name: "", dir: -1 }]);
              }}
            >
              Remove
            </button>
          </div>
        ))}
        <div className="row" style={{ marginTop: 8 }}>
          <button
            type="button"
            className="ghost"
            onClick={() => {
              setActivePreset("");
              setRows([...rows, { name: "", dir: -1 }]);
            }}
          >
            + Add target
          </button>
          <button type="button" onClick={() => run(undefined, true)} disabled={loading}>
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
              if (parts.length) fill(parts.join(", "), "disease-repurposing");
            }}
          >
            Ask Agent
          </button>
        </div>

        <div className="small muted" style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 5 }}>
          <div className="chip-row">
            <strong>PROGENy:</strong>
            {PROGENY_IDS.map((id) => (
              <button key={id} type="button" className="chip mono" style={{ padding: "2px 7px", fontSize: 11 }} onClick={() => addQuickTarget(id)}>
                +{id}
              </button>
            ))}
          </div>
          <div className="chip-row">
            <strong>CollecTRI TFs:</strong>
            {TF_IDS.map((id) => (
              <button key={id} type="button" className="chip mono" style={{ padding: "2px 7px", fontSize: 11 }} onClick={() => addQuickTarget(id)}>
                +{id}
              </button>
            ))}
          </div>
          <div className="chip-row">
            <strong>Renal modules:</strong>
            {MODULE_IDS.map((id) => (
              <button key={id} type="button" className="chip mono" style={{ padding: "2px 7px", fontSize: 11 }} onClick={() => addQuickTarget(id)}>
                +{id}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div className="small" style={{ color: "var(--bad)", marginTop: 8 }}>
            {error}
          </div>
        )}
      </div>

      {data && (
        <div className="card" style={{ marginTop: 12 }}>
          <div className="row">
            <h2 style={{ margin: 0 }}>Candidate Drugs ({data.results?.length || 0})</h2>
            <span className="spacer" />
            <span className="small muted">
              Matched {data.used?.length || 0} · Unrecognized {(data.missing || []).join(", ") || "None"}
            </span>
          </div>
          <div className="scroll" style={{ marginTop: 8 }}>
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
