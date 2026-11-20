"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Chart from "@/components/Chart";
import Structure from "@/components/Structure";

function fmt(v: any) {
  return v == null ? "—" : Number(v).toFixed(1);
}

export default function CompoundView({ id }: { id: string }) {
  const [data, setData] = useState<any>(null);
  const [explain, setExplain] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!id) return;
    setData(null);
    setExplain(null);
    setError("");
    fetch(`/api/v1/compound/${encodeURIComponent(id)}`).then(async (r) => {
      const body = await r.json();
      if (!r.ok) throw new Error(body.detail || "not found");
      setData(body);
    }).catch((e) => setError(String(e.message || e)));
    fetch(`/api/v1/compound/${encodeURIComponent(id)}/explain`).then((r) => r.json())
      .then(setExplain).catch(() => {});
  }, [id]);

  const funcChart = useMemo(() => {
    if (!data?.functional_activity?.renal_modules) return null;
    const entries = Object.entries(data.functional_activity.renal_modules);
    return {
      tooltip: { trigger: "axis" },
      grid: { left: 90, right: 20, top: 10, bottom: 20 },
      xAxis: { type: "value" },
      yAxis: { type: "category", data: entries.map(([k]) => k).reverse() },
      series: [{ type: "bar", data: entries.map(([, v]) => v).reverse(), itemStyle: { color: "#0f6cbd" } }],
    };
  }, [data]);

  if (!id) return <div className="card">请提供化合物 ID 或名称（例如 <Link href="/compound/?id=dexamethasone">dexamethasone</Link>）。</div>;
  if (error) return <div className="card">未找到化合物：{error}</div>;
  if (!data) return <div className="muted">加载中…</div>;

  const c = data.compound;
  return (
    <>
      <div className="page-head"><h1>{c.pert_iname || c.pert_id}</h1>
        <span className="badge grey">{c.pert_id}</span>
        {c.clinical_phase && <span className="badge green">{c.clinical_phase}</span>}
      </div>
      <div className="sub">{c.moa || "暂无 MoA 注释"}</div>

      <div className="grid cols-2">
        <div className="card">
          <h2>化学结构</h2>
          <Structure smiles={c.canonical_smiles || c.input_smiles} />
          <div className="kv" style={{ marginTop: 8 }}>
            <div>InChIKey</div><div className="mono small">{c.inchikey || "—"}</div>
            <div>母核 (IK-14)</div><div className="mono small">{c.inchikey14 || "—"}</div>
            <div>MW / LogP</div><div>{c.mw ? Number(c.mw).toFixed(1) : "—"} / {c.logp ? Number(c.logp).toFixed(2) : "—"}</div>
            <div>TPSA / QED</div><div>{c.tpsa ? Number(c.tpsa).toFixed(1) : "—"} / {c.qed ? Number(c.qed).toFixed(3) : "—"}</div>
            <div>Lipinski 违规</div><div>{c.lipinski_violations ?? "—"}</div>
            <div>PAINS</div><div>{c.pains_alerts ?? "—"}</div>
            <div>K-PRL λ</div><div>{c.kprl_lambda != null ? Number(c.kprl_lambda).toFixed(3) : "—"}</div>
            <div>签名数</div><div>{c.n_sigs ?? "—"}</div>
          </div>
        </div>

        <div className="card">
          <h2>肾脏安全与机制</h2>
          <div className="kv">
            <div>T-DIKI v2 门控风险</div><div>{Number(data.tdiki?.prob || 0).toFixed(3)}</div>
            <div>结构专家</div><div>{data.tdiki?.struct != null ? Number(data.tdiki.struct).toFixed(3) : "—"}</div>
            <div>HA1E 肾上皮毒理</div><div>{data.tdiki?.tx != null ? Number(data.tdiki.tx).toFixed(3) : "无实测（仅结构）"}</div>
            <div>T-DIKI 分层</div><div>{data.tdiki?.tier}</div>
            <div>DIRIL 金标准</div><div>
              {data.tdiki?.diril_label === 1 ? <span className="badge red">肾毒阳性</span>
                : data.tdiki?.diril_label === 0 ? <span className="badge green">肾毒阴性</span>
                  : <span className="badge grey">未收录</span>}</div>
          </div>
          {explain?.contributions?.length ? (
            <>
              <h2 style={{ marginTop: 16 }}>T-DIKI 归因（线性模型贡献）</h2>
              <table><thead><tr><th>特征</th><th>贡献</th><th>取值</th></tr></thead>
                <tbody>{explain.contributions.map((x: any) => (
                  <tr key={x.feature}><td className="mono small">{x.feature}</td>
                    <td>{Number(x.contribution).toFixed(3)}</td>
                    <td>{Number(x.value).toFixed(3)}</td></tr>))}</tbody></table>
            </>
          ) : null}
          <h2 style={{ marginTop: 16 }}>同母核兄弟</h2>
          <div className="row" style={{ gap: 6 }}>
            {(data.scaffold_siblings || []).slice(0, 12).map((p: string) => (
              <Link key={p} className="badge grey" href={`/compound/?id=${encodeURIComponent(p)}`}>{p}</Link>
            ))}
          </div>
        </div>
      </div>

      <div className="grid cols-2" style={{ marginTop: 16 }}>
        <div className="card">
          <h2>Top 上调 / 下调基因（K-PRL）</h2>
          <div className="grid cols-2">
            <table><thead><tr><th>上调</th><th>z</th></tr></thead>
              <tbody>{data.top_up_genes.map((g: any) => (
                <tr key={g.symbol}><td>{g.symbol}</td><td>{Number(g.z).toFixed(2)}</td></tr>))}</tbody></table>
            <table><thead><tr><th>下调</th><th>z</th></tr></thead>
              <tbody>{data.top_down_genes.map((g: any) => (
                <tr key={g.symbol}><td>{g.symbol}</td><td>{Number(g.z).toFixed(2)}</td></tr>))}</tbody></table>
          </div>
        </div>

        <div className="card">
          <h2>肾病病理模块活性</h2>
          {funcChart ? <Chart option={funcChart} height={360} /> : <div className="muted small">无功能矩阵</div>}
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>药物靶点与肾脏区室表达（nCPM / nTPM）</h2>
        {data.targets?.length ? (
          <div className="scroll">
            <table><thead><tr>
              <th>靶点</th><th>MoA</th><th>PT</th><th>TAL</th><th>DCT</th><th>CD</th>
              <th>足细胞</th><th>内皮</th><th>免疫</th><th>HPA 肾</th><th>GTEx 皮质</th>
            </tr></thead><tbody>
              {data.targets.map((t: any) => (
                <tr key={t.target_symbol}>
                  <td><Link href={`/target/?symbol=${encodeURIComponent(t.target_symbol)}`}>{t.target_symbol}</Link></td>
                  <td className="small">{t.moa || "—"}</td>
                  <td>{fmt(t.sc_pt)}</td><td>{fmt(t.sc_tal)}</td><td>{fmt(t.sc_dct)}</td>
                  <td>{fmt(t.sc_cd)}</td><td>{fmt(t.sc_podocyte)}</td><td>{fmt(t.sc_endo)}</td>
                  <td>{fmt(t.sc_immune)}</td><td>{fmt(t.hpa_kidney_ntpm)}</td><td>{fmt(t.gtex_cortex_tpm)}</td>
                </tr>))}
            </tbody></table>
          </div>
        ) : <div className="muted small">暂无直接靶点注释</div>}
      </div>
    </>
  );
}
