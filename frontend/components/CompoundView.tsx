"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { HorizontalBarChart } from "@/components/Chart";
import Structure from "@/components/Structure";
import { DikiBadge, DirilBadge } from "@/components/Badges";
import { useAgent } from "@/components/AgentContext";
import { apiJson } from "@/lib/api";

function fmt(v: any) {
  return v == null ? "—" : Number(v).toFixed(1);
}

export default function CompoundView({ id }: { id: string }) {
  const { fill } = useAgent();
  const [data, setData] = useState<any>(null);
  const [explain, setExplain] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    setData(null);
    setExplain(null);
    setError("");
    apiJson(`/api/v1/compound/${encodeURIComponent(id)}`)
      .then(setData)
      .catch((e) => setError(String(e.message || e)));
    apiJson(`/api/v1/compound/${encodeURIComponent(id)}/explain`)
      .then(setExplain)
      .catch(() => {});
  }, [id]);

  const moduleItems = useMemo(() => {
    if (!data?.functional_activity?.renal_modules) return [];
    return Object.entries(data.functional_activity.renal_modules).map(
      ([label, value]) => ({ label, value: Number(value) || 0 })
    );
  }, [data]);

  if (!id) {
    return (
      <div className="card">
        Provide a compound name, BRD ID, or InChIKey (e.g.,{" "}
        <Link href="/compound/?id=dexamethasone" prefetch={false}>
          dexamethasone
        </Link>
        ).
      </div>
    );
  }
  if (error) return <div className="card">Compound not found: {error}</div>;
  if (!data) {
    return (
      <div className="card row">
        <span className="spinner" />
        <span className="muted">Loading compound profile...</span>
      </div>
    );
  }

  const c = data.compound;
  const label = c.pert_iname || c.pert_id;
  return (
    <>
      <div className="page-head">
        <h1>{label}</h1>
        <span className="badge grey mono">{c.pert_id}</span>
        {c.clinical_phase && <span className="badge green">{c.clinical_phase}</span>}
        <span className="spacer" />
        <Link href={`/structure/?q=${encodeURIComponent(c.pert_id)}`} prefetch={false}>
          <button type="button" className="ghost mini">
            Find structural analogs →
          </button>
        </Link>
        <button
          type="button"
          className="ghost mini"
          onClick={() => fill(`Profile ${label}`)}
        >
          Ask Agent
        </button>
      </div>
      <div className="sub">{c.moa || "No MoA annotation curated"}</div>

      <div className="grid cols-2">
        <div className="card">
          <h2>Chemical structure</h2>
          <Structure smiles={c.canonical_smiles || c.input_smiles} />
          <div className="kv" style={{ marginTop: 12 }}>
            <div>InChIKey</div>
            <div className="mono small">{c.inchikey || "—"}</div>
            <div>Scaffold (IK-14)</div>
            <div className="mono small">{c.inchikey14 || "—"}</div>
            <div>MW / LogP</div>
            <div>
              {c.mw ? Number(c.mw).toFixed(1) : "—"} / {c.logp ? Number(c.logp).toFixed(2) : "—"}
            </div>
            <div>TPSA / QED</div>
            <div>
              {c.tpsa ? Number(c.tpsa).toFixed(1) : "—"} / {c.qed ? Number(c.qed).toFixed(3) : "—"}
            </div>
            <div>Lipinski violations</div>
            <div>{c.lipinski_violations ?? "—"}</div>
            <div>PAINS alerts</div>
            <div>{c.pains_alerts ?? "—"}</div>
            <div>K-PRL λ</div>
            <div>{c.kprl_lambda != null ? Number(c.kprl_lambda).toFixed(3) : "—"}</div>
            <div>Signatures merged</div>
            <div>{c.n_sigs ?? "—"}</div>
          </div>
        </div>

        <div className="card">
          <h2>Kidney safety & mechanism</h2>
          <div className="kv">
            <div>T-DIKI v2 gated risk</div>
            <div>{Number(data.tdiki?.prob || 0).toFixed(3)}</div>
            <div>Structure expert</div>
            <div>{data.tdiki?.struct != null ? Number(data.tdiki.struct).toFixed(3) : "—"}</div>
            <div>HA1E epithelial tox</div>
            <div>
              {data.tdiki?.tx != null
                ? Number(data.tdiki.tx).toFixed(3)
                : "Not measured (structure only)"}
            </div>
            <div>T-DIKI tier</div>
            <div>
              <DikiBadge tier={data.tdiki?.tier} />
            </div>
            <div>DIRIL gold standard</div>
            <div>
              <DirilBadge value={data.tdiki?.diril_label} />
            </div>
          </div>
          {explain?.contributions?.length ? (
            <>
              <h2 style={{ marginTop: 16 }}>T-DIKI attribution (structure contributions)</h2>
              <table>
                <thead>
                  <tr>
                    <th>Feature</th>
                    <th>Contribution</th>
                    <th>Value</th>
                  </tr>
                </thead>
                <tbody>
                  {explain.contributions.map((x: any) => (
                    <tr key={x.feature}>
                      <td className="mono small">{x.feature}</td>
                      <td>{Number(x.contribution).toFixed(3)}</td>
                      <td>{Number(x.value).toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : null}
          <h2 style={{ marginTop: 16 }}>Scaffold siblings (same InChIKey-14)</h2>
          <div className="chip-row">
            {(data.scaffold_siblings || []).slice(0, 12).map((p: string) => (
              <Link
                key={p}
                prefetch={false}
                className="badge grey mono"
                href={`/compound/?id=${encodeURIComponent(p)}`}
              >
                {p}
              </Link>
            ))}
          </div>
        </div>
      </div>

      <div className="grid cols-2" style={{ marginTop: 16 }}>
        <div className="card">
          <h2>Top up / down genes (K-PRL)</h2>
          <div className="grid cols-2">
            <table>
              <thead>
                <tr>
                  <th>Up-regulated</th>
                  <th>Z-score</th>
                </tr>
              </thead>
              <tbody>
                {data.top_up_genes.map((g: any) => (
                  <tr key={g.symbol}>
                    <td>
                      <Link href={`/target/?symbol=${encodeURIComponent(g.symbol)}`} prefetch={false}>
                        {g.symbol}
                      </Link>
                    </td>
                    <td className="mono">{Number(g.z).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <table>
              <thead>
                <tr>
                  <th>Down-regulated</th>
                  <th>Z-score</th>
                </tr>
              </thead>
              <tbody>
                {data.top_down_genes.map((g: any) => (
                  <tr key={g.symbol}>
                    <td>
                      <Link href={`/target/?symbol=${encodeURIComponent(g.symbol)}`} prefetch={false}>
                        {g.symbol}
                      </Link>
                    </td>
                    <td className="mono">{Number(g.z).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="card">
          <h2>Renal pathology module activity</h2>
          {moduleItems.length > 0 ? (
            <HorizontalBarChart items={moduleItems} height={320} />
          ) : (
            <div className="muted small">No functional matrix available</div>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>Drug targets & kidney compartment expression (nCPM / nTPM)</h2>
        {data.targets?.length ? (
          <div className="scroll">
            <table>
              <thead>
                <tr>
                  <th>Target</th>
                  <th>MoA</th>
                  <th>PT</th>
                  <th>TAL</th>
                  <th>DCT</th>
                  <th>CD</th>
                  <th>Podocyte</th>
                  <th>Endothelium</th>
                  <th>Immune</th>
                  <th>HPA kidney</th>
                  <th>GTEx cortex</th>
                </tr>
              </thead>
              <tbody>
                {data.targets.map((t: any) => (
                  <tr key={t.target_symbol}>
                    <td>
                      <Link
                        href={`/target/?symbol=${encodeURIComponent(t.target_symbol)}`}
                        prefetch={false}
                      >
                        {t.target_symbol}
                      </Link>
                    </td>
                    <td className="small">{t.moa || "—"}</td>
                    <td>{fmt(t.sc_pt)}</td>
                    <td>{fmt(t.sc_tal)}</td>
                    <td>{fmt(t.sc_dct)}</td>
                    <td>{fmt(t.sc_cd)}</td>
                    <td>{fmt(t.sc_podocyte)}</td>
                    <td>{fmt(t.sc_endo)}</td>
                    <td>{fmt(t.sc_immune)}</td>
                    <td>{fmt(t.hpa_kidney_ntpm)}</td>
                    <td>{fmt(t.gtex_cortex_tpm)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="muted small">No direct target annotations</div>
        )}
      </div>
    </>
  );
}
