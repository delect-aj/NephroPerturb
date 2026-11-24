"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import Structure from "@/components/Structure";
import { TanimotoBar } from "@/components/Badges";
import { useAgent } from "@/components/AgentContext";
import { apiJson } from "@/lib/api";
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
    setResolvedLabel("");

    try {
      let body: any;
      if (isSmilesInput(clean)) {
        setQuerySmiles(clean);
        setResolvedLabel("SMILES query");
        body = { smiles: clean, top_k: 20 };
      } else {
        setQuerySmiles(null);
        const cBody = await apiJson(`/api/v1/compound/${encodeURIComponent(clean)}`);
        const pid = cBody.compound?.pert_id || clean;
        const pname = cBody.compound?.pert_iname || pid;
        setQuerySmiles(cBody.compound?.canonical_smiles || cBody.compound?.input_smiles || null);
        setResolvedLabel(`${pname} (${pid})`);
        body = { pert_id: pid, top_k: 20 };
      }

      const payload = await apiJson("/api/v1/similarity/structure", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setResults(payload.results || []);
    } catch (e: any) {
      setError(String(e.message || e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("q") || STRUCTURE_PRESETS[0].query;
    runSearch(q);
  }, []);

  const tableCard = results.length > 0 && (
    <div className="card">
      <div className="row">
        <h2 style={{ margin: 0 }}>Structural Neighbors ({results.length})</h2>
        <span className="spacer" />
        {resolvedLabel && <span className="badge grey">{resolvedLabel}</span>}
      </div>
      <div className="scroll" style={{ marginTop: 10 }}>
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>Compound</th>
              <th>ECFP4 Tanimoto</th>
              <th>MoA</th>
              <th>Phase</th>
            </tr>
          </thead>
          <tbody>
            {results.map((r: any, i: number) => (
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
                <td>
                  <TanimotoBar value={r.tanimoto} />
                </td>
                <td className="small">{r.moa || "—"}</td>
                <td className="small">{r.clinical_phase || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  return (
    <>
      <div className="page-head">
        <h1>Structure Search & MoA Inference</h1>
      </div>
      <div className="sub">
        2048-bit Morgan ECFP4 Tanimoto search and MoA inference from SMILES or compound IDs.
      </div>

      <div className="card" style={{ marginBottom: 12 }}>
        <div className="row">
          <input
            type="text"
            style={{ flex: 1, minWidth: 240 }}
            value={query}
            placeholder="SMILES string, compound name, or BRD ID..."
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
            onClick={() => fill(`Find compounds structurally similar to ${query.trim()} and infer MoA & kidney safety`, "structure-moa-evidence")}
          >
            Ask Agent
          </button>
        </div>

        <div className="chip-row" style={{ marginTop: 8 }}>
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
          <div className="small" style={{ color: "var(--bad)", marginTop: 8 }}>
            {error}
          </div>
        )}
      </div>

      {querySmiles ? (
        <div className="split-aside">
          <div className="card">
            <h2>Query 2D Structure</h2>
            <Structure smiles={querySmiles} width={300} height={210} />
            <div className="small mono muted" style={{ marginTop: 8, wordBreak: "break-all" }}>
              {querySmiles}
            </div>
          </div>
          {tableCard || (
            <div className="card row">
              <span className="spinner" />
              <span className="muted">Scanning 21,299 compounds...</span>
            </div>
          )}
        </div>
      ) : (
        tableCard
      )}
    </>
  );
}
