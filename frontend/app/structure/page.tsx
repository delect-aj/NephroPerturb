"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import Structure from "@/components/Structure";
import { useAgent } from "@/components/AgentContext";
import { STRUCTURE_PRESETS } from "@/lib/examples";

function isSmilesInput(q: string) {
  const s = q.trim();
  if (/^BRD-/i.test(s)) return false;
  return /[()=#\[\]]/.test(s) || /[cnoCNO]\d/.test(s);
}

export default function StructureSearchPage() {
  const { fill } = useAgent();
  const [query, setQuery] = useState(STRUCTURE_PRESETS[0].query);
  const [querySmiles, setQuerySmiles] = useState<string | null>(null);
  const [resolvedLabel, setResolvedLabel] = useState("");
  const [results, setResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function runSearch(inputStr?: string) {
    const clean = (inputStr !== undefined ? inputStr : query).trim();
    if (!clean) return;
    if (inputStr !== undefined) setQuery(clean);
    setLoading(true);
    setError("");
    setResults([]);
    setResolvedLabel("");

    try {
      let body: any;
      if (isSmilesInput(clean)) {
        setQuerySmiles(clean);
        setResolvedLabel(`SMILES query`);
        body = { smiles: clean, top_k: 20 };
      } else {
        setQuerySmiles(null);
        const cr = await fetch(`/api/v1/compound/${encodeURIComponent(clean)}`);
        const cBody = await cr.json();
        if (!cr.ok) throw new Error(cBody.detail || `Compound '${clean}' not found`);
        const pid = cBody.compound?.pert_id || clean;
        const pname = cBody.compound?.pert_iname || pid;
        setResolvedLabel(`${pname} (${pid})`);
        body = { pert_id: pid, top_k: 20 };
      }

      const res = await fetch("/api/v1/similarity/structure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.detail || "Structure search failed");
      setResults(payload.results || []);
    } catch (e: any) {
      setError(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) runSearch(q);
  }, []);

  return (
    <>
      <div className="page-head">
        <h1>Structure Search & MoA Inference</h1>
      </div>
      <div className="sub">
        Search 21,299 compounds by 2048-bit Morgan ECFP4 Tanimoto similarity using a SMILES string, drug name, or BRD ID.
      </div>

      <div className="card" style={{ marginBottom: 18 }}>
        <label>SMILES string, compound name, or BRD ID</label>
        <div className="row">
          <input
            type="text"
            value={query}
            placeholder="e.g. CC(=O)OC1=CC=CC=C1C(=O)O or dexamethasone"
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") runSearch();
            }}
          />
          <button type="button" onClick={() => runSearch()} disabled={loading}>
            {loading && <span className="spinner" />}
            {loading ? "Searching..." : "Search"}
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => fill(`Find compounds structurally similar to ${query.trim()}`)}
          >
            Ask Agent
          </button>
        </div>

        <div className="chip-row" style={{ marginTop: 12 }}>
          <span className="small muted">Examples:</span>
          {STRUCTURE_PRESETS.map((p) => (
            <button
              key={p.label}
              type="button"
              className="chip"
              onClick={() => runSearch(p.query)}
            >
              {p.label}
            </button>
          ))}
        </div>

        {error && (
          <div className="small" style={{ color: "var(--bad)", marginTop: 10 }}>
            {error}
          </div>
        )}
      </div>

      {querySmiles && (
        <div className="card" style={{ marginBottom: 18, maxWidth: 440 }}>
          <h2>Query 2D Structure</h2>
          <Structure smiles={querySmiles} />
        </div>
      )}

      {results.length > 0 && (
        <div className="card">
          <div className="row">
            <h2 style={{ margin: 0 }}>Structural Neighbors ({results.length})</h2>
            <span className="spacer" />
            {resolvedLabel && <span className="badge grey">{resolvedLabel}</span>}
          </div>
          <div className="scroll" style={{ marginTop: 12 }}>
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Compound</th>
                  <th>ECFP4 Tanimoto</th>
                  <th>MoA</th>
                  <th>Clinical Phase</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r: any, i: number) => {
                  const sim = Number(r.tanimoto || 0);
                  const pct = Math.max(0, Math.min(100, Math.round(sim * 100)));
                  return (
                    <tr key={r.pert_id}>
                      <td className="mono muted">{i + 1}</td>
                      <td>
                        <Link href={`/compound/?id=${encodeURIComponent(r.pert_id)}`}>
                          {r.pert_iname || r.pert_id}
                        </Link>
                        <div className="small muted mono">{r.pert_id}</div>
                      </td>
                      <td>
                        <div className="tanimoto-wrap">
                          <span className="mono">{sim.toFixed(3)}</span>
                          <div className="tanimoto-bar">
                            <div className="tanimoto-fill" style={{ width: `${pct}%` }} />
                          </div>
                        </div>
                      </td>
                      <td className="small">{r.moa || "—"}</td>
                      <td className="small">{r.clinical_phase || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
