"use client";
import { useEffect, useState } from "react";
import Link from "next/link";

export default function CasesPage() {
  const [cases, setCases] = useState<any[]>([]);
  const [active, setActive] = useState<any>(null);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch("/api/v1/cases").then((r) => r.json()).then((d) => {
      setCases(d.cases || []);
      const wanted = new URLSearchParams(window.location.search).get("run");
      if (wanted) run(wanted);
    }).catch(() => {});
  }, []);

  async function run(caseId: string) {
    setLoading(true); setData(null);
    try {
      const res = await fetch(`/api/v1/cases/${caseId}`);
      setData(await res.json());
      setActive(caseId);
    } finally { setLoading(false); }
  }

  return (
    <>
      <div className="page-head"><h1>肾病经典案例库</h1></div>
      <div className="sub">真实人源肾活检队列（GEO series matrix，经 QC：组样本量、基因映射覆盖率与生物学阳性通路校验），含平台、疾病/对照数与校验和溯源。</div>
      <div className="grid cols-3">
        {cases.map((c) => (
          <div className="card" key={c.case_id}>
            <h2>{c.case_id} · {c.disease_name}</h2>
            <div className="small muted">区室：{c.compartment} · {c.gse || c.dataset_accession} · {c.platform || "—"}</div>
            <div className="small muted">疾病 n={c.n_disease ?? "—"} / 对照 n={c.n_control ?? "—"} · PMID {c.pmid || "—"}</div>
            {c.matrix_sha256 && <div className="small muted mono">sha256 {String(c.matrix_sha256).slice(0, 16)}…</div>}
            <div className="row" style={{ marginTop: 10 }}>
              <button onClick={() => run(c.case_id)} disabled={loading}>运行逆转检索</button>
            </div>
          </div>
        ))}
      </div>

      {data && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="row"><h2 style={{ margin: 0 }}>{active} 候选药物</h2><span className="spacer" />
            <span className="small muted mono">job {data.job_id}</span></div>
          <div className="scroll" style={{ marginTop: 10 }}>
            <table><thead><tr><th>#</th><th>化合物</th><th>RTPS</th><th>RenalConn</th>
              <th>分期</th><th>T-DIKI</th><th>DIRIL</th></tr></thead>
              <tbody>{(data.results || []).map((r: any, i: number) => (
                <tr key={r.pert_id}><td>{i + 1}</td>
                  <td><Link href={`/compound/${r.pert_id}`}>{r.pert_iname || r.pert_id}</Link></td>
                  <td>{Number(r.rtps).toFixed(1)}</td><td>{Number(r.renalconn).toFixed(1)}</td>
                  <td className="small">{r.clinical_phase || "—"}</td>
                  <td>{r.tdiki_tier || "NA"}</td>
                  <td>{r.diril_label === 1 ? "阳性" : r.diril_label === 0 ? "阴性" : "—"}</td></tr>))}</tbody></table>
          </div>
        </div>
      )}
    </>
  );
}
