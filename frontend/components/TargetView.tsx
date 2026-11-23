"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { HorizontalBarChart } from "@/components/Chart";
import { useAgent } from "@/components/AgentContext";
import { apiJson } from "@/lib/api";

const LABELS: Record<string, string> = {
  sc_pt: "Proximal tubule (PT)",
  sc_tal: "Thick ascending limb (TAL)",
  sc_dct: "Distal convoluted tubule (DCT)",
  sc_cd: "Collecting duct (CD)",
  sc_podocyte: "Podocyte",
  sc_endo: "Endothelium",
  sc_immune: "Immune",
  hpa_kidney_ntpm: "HPA kidney (nTPM)",
  gtex_cortex_tpm: "GTEx cortex (TPM)",
  gtex_medulla_tpm: "GTEx medulla (TPM)",
};

export default function TargetView({ symbol }: { symbol: string }) {
  const { fill } = useAgent();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!symbol) return;
    setData(null);
    setError("");
    apiJson(`/api/v1/target/${encodeURIComponent(symbol)}`)
      .then(setData)
      .catch((e) => setError(String(e.message || e)));
  }, [symbol]);

  const exprItems = useMemo(() => {
    if (!data?.kidney_expression) return [];
    return Object.entries(data.kidney_expression)
      .filter(([k, v]) => LABELS[k] && v != null)
      .map(([k, v]) => ({ label: LABELS[k], value: Number(v) || 0 }));
  }, [data]);

  if (error) return <div className="card">Gene not found: {error}</div>;
  if (!data) {
    return (
      <div className="card row">
        <span className="spinner" />
        <span className="muted">Loading target genetics...</span>
      </div>
    );
  }

  return (
    <>
      <div className="page-head">
        <h1>{data.gene.symbol}</h1>
        <span className="badge grey mono">Entrez {data.gene.entrez_id}</span>
        {data.gene.is_landmark === 1 && <span className="badge green">Landmark</span>}
        {data.gene.is_bing === 1 && <span className="badge blue">BING</span>}
        <span className="spacer" />
        <button
          type="button"
          className="ghost mini"
          onClick={() => fill(`Which compounds mimic knockdown of ${data.gene.symbol}?`)}
        >
          Ask Agent
        </button>
      </div>
      <div className="sub">{data.gene.title || `Target ${data.gene.symbol}`}</div>

      <div className="grid cols-2">
        <div className="card">
          <h2>Kidney compartment expression</h2>
          {exprItems.length > 0 ? (
            <HorizontalBarChart items={exprItems} color="#14b8a6" height={320} />
          ) : (
            <div className="muted small">No expression data available</div>
          )}
        </div>
        <div className="card">
          <h2>Direct targeting drugs ({data.targeting_drugs?.length || 0})</h2>
          <div className="scroll" style={{ maxHeight: 360 }}>
            {data.targeting_drugs?.length ? (
              <table>
                <thead>
                  <tr>
                    <th>Compound</th>
                    <th>Phase</th>
                    <th>MoA</th>
                  </tr>
                </thead>
                <tbody>
                  {data.targeting_drugs.map((d: any) => (
                    <tr key={d.pert_id}>
                      <td>
                        <Link
                          href={`/compound/?id=${encodeURIComponent(d.pert_id)}`}
                          prefetch={false}
                        >
                          {d.pert_iname || d.pert_id}
                        </Link>
                        <div className="small muted mono">{d.pert_id}</div>
                      </td>
                      <td className="small">{d.clinical_phase || "—"}</td>
                      <td className="small">{d.moa || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="muted small" style={{ padding: 12 }}>
                No curated direct targeting drugs
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="grid cols-2" style={{ marginTop: 16 }}>
        <div className="card">
          <h2>LINCS genetic perturbations</h2>
          {(data.genetic_perturbations || []).length ? (
            <table>
              <thead>
                <tr>
                  <th>pert_id</th>
                  <th>Type</th>
                  <th>Signatures</th>
                </tr>
              </thead>
              <tbody>
                {data.genetic_perturbations.map((g: any) => (
                  <tr key={g.pert_id}>
                    <td className="mono small">{g.pert_id}</td>
                    <td>{g.pert_type}</td>
                    <td>{g.n_sigs}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="muted small">No matching genetic perturbations</div>
          )}
        </div>
        <div className="card">
          <h2>Compounds mimicking gene knockdown</h2>
          <div className="scroll" style={{ maxHeight: 360 }}>
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Compound</th>
                  <th>Cosine Similarity</th>
                </tr>
              </thead>
              <tbody>
                {(data.mimicking_compounds || []).map((c: any, i: number) => (
                  <tr key={c.pert_id}>
                    <td className="mono muted">{i + 1}</td>
                    <td>
                      <Link
                        href={`/compound/?id=${encodeURIComponent(c.pert_id)}`}
                        prefetch={false}
                      >
                        {c.pert_iname || c.pert_id}
                      </Link>
                    </td>
                    <td className="mono">{Number(c.similarity).toFixed(3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </>
  );
}
