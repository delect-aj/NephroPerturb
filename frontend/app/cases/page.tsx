"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { DikiBadge, DirilBadge } from "@/components/Badges";
import { useAgent } from "@/components/AgentContext";
import { apiJson } from "@/lib/api";

export default function CasesPage() {
  const { fill } = useAgent();
  const [cases, setCases] = useState<any[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    apiJson("/api/v1/cases")
      .then((d) => {
        setCases(d.cases || []);
        const wanted = new URLSearchParams(window.location.search).get("run");
        if (wanted) run(wanted);
      })
      .catch((e) => setError(String(e.message || e)));
  }, []);

  async function run(caseId: string) {
    setLoading(true);
    setError("");
    setData(null);
    setActive(caseId);
    try {
      const payload = await apiJson(
        `/api/v1/cases/${encodeURIComponent(caseId)}`,
        undefined,
        45000
      );
      setData(payload);
    } catch (e: any) {
      setError(`Failed to run ${caseId}: ${String(e.message || e)}`);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>Disease Cohorts</h1>
      </div>
      <div className="sub">
        10 QC-validated human kidney biopsy cohorts (GEO) with accession and SHA-256 provenance.
      </div>

      {error && (
        <div
          className="card"
          style={{
            marginBottom: 12,
            borderColor: "#fca5a5",
            background: "#fef2f2",
            color: "var(--bad)",
          }}
        >
          {error}
        </div>
      )}

      <div className="grid cols-2">
        {cases.map((c) => (
          <div className="card cohort-card" key={c.case_id}>
            <div className="cohort-meta">
              <div className="row" style={{ gap: 6, marginBottom: 3 }}>
                <strong style={{ fontSize: 14 }}>{c.case_id}</strong>
                <span className="badge blue">{c.disease_name}</span>
                <span className="badge grey mono">{c.gse || c.dataset_accession}</span>
              </div>
              <div className="small muted">{c.compartment}</div>
              <div className="small muted">
                n={c.n_disease ?? "—"} disease / {c.n_control ?? "—"} control · {c.platform || "—"} · PMID{" "}
                {c.pmid || "—"}
                {c.matrix_sha256 ? ` · sha256 ${String(c.matrix_sha256).slice(0, 12)}…` : ""}
              </div>
            </div>
            <div className="cohort-actions">
              <button
                type="button"
                className="mini"
                onClick={() => run(c.case_id)}
                disabled={loading}
              >
                {loading && active === c.case_id && <span className="spinner" />}
                {loading && active === c.case_id ? "Running..." : "Run"}
              </button>
              <button
                type="button"
                className="ghost mini"
                onClick={() => fill(`Run the ${c.case_id} case`)}
              >
                Agent
              </button>
            </div>
          </div>
        ))}
      </div>

      {data && (
        <div className="card" style={{ marginTop: 14 }}>
          <div className="row">
            <h2 style={{ margin: 0 }}>{active} Candidate Drugs ({data.results?.length || 0})</h2>
            <span className="spacer" />
            <span className="small muted mono">job {data.job_id}</span>
          </div>
          <div className="scroll" style={{ marginTop: 8 }}>
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Compound</th>
                  <th>RTPS</th>
                  <th>RenalConn</th>
                  <th>Phase</th>
                  <th>T-DIKI</th>
                  <th>DIRIL</th>
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
                    <td className="mono">{Number(r.rtps).toFixed(1)}</td>
                    <td className="mono">{Number(r.renalconn).toFixed(1)}</td>
                    <td className="small">{r.clinical_phase || "—"}</td>
                    <td><DikiBadge tier={r.tdiki_tier} /></td>
                    <td><DirilBadge value={r.diril_label} /></td>
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
