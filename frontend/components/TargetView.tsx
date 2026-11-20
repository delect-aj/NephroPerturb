"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Chart from "@/components/Chart";

const LABELS: Record<string, string> = {
  sc_pt: "近端小管 PT", sc_tal: "髓袢 TAL", sc_dct: "远端小管 DCT",
  sc_cd: "集合管 CD", sc_podocyte: "足细胞", sc_endo: "内皮", sc_immune: "免疫",
  hpa_kidney_ntpm: "HPA 肾 (nTPM)", gtex_cortex_tpm: "GTEx 皮质 (TPM)",
  gtex_medulla_tpm: "GTEx 髓质 (TPM)",
};

export default function TargetView({ symbol }: { symbol: string }) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!symbol) return;
    setData(null);
    setError("");
    fetch(`/api/v1/target/${encodeURIComponent(symbol)}`).then(async (r) => {
      const body = await r.json();
      if (!r.ok) throw new Error(body.detail || "not found");
      setData(body);
    }).catch((e) => setError(String(e.message || e)));
  }, [symbol]);

  const chart = useMemo(() => {
    if (!data?.kidney_expression) return null;
    const entries = Object.entries(data.kidney_expression)
      .filter(([k, v]) => LABELS[k] && v != null);
    return {
      tooltip: { trigger: "axis" },
      grid: { left: 110, right: 24, top: 10, bottom: 20 },
      xAxis: { type: "value" },
      yAxis: { type: "category", data: entries.map(([k]) => LABELS[k]) },
      series: [{ type: "bar", data: entries.map(([, v]) => v), itemStyle: { color: "#0f6cbd" } }],
    };
  }, [data]);

  if (error) return <div className="card">未找到基因：{error}</div>;
  if (!data) return <div className="muted">加载中…</div>;

  return (
    <>
      <div className="page-head"><h1>{data.gene.symbol}</h1>
        <span className="badge grey">Entrez {data.gene.entrez_id}</span>
        {data.gene.is_landmark === 1 && <span className="badge green">Landmark</span>}
        {data.gene.is_bing === 1 && <span className="badge grey">BING</span>}
      </div>
      <div className="sub">{data.gene.title}</div>

      <div className="grid cols-2">
        <div className="card"><h2>肾脏区室表达</h2>
          {chart ? <Chart option={chart} height={360} /> : <div className="muted small">无表达数据</div>}
        </div>
        <div className="card"><h2>直接靶向药物（{data.targeting_drugs?.length || 0}）</h2>
          <div className="scroll" style={{ maxHeight: 360 }}>
            <table><thead><tr><th>化合物</th><th>MoA</th></tr></thead>
              <tbody>{(data.targeting_drugs || []).map((d: any) => (
                <tr key={d.pert_id}><td><Link href={`/compound/?id=${encodeURIComponent(d.pert_id)}`}>{d.pert_id}</Link></td>
                  <td className="small">{d.moa || "—"}</td></tr>))}</tbody></table>
          </div>
        </div>
      </div>

      <div className="grid cols-2" style={{ marginTop: 16 }}>
        <div className="card"><h2>遗传扰动记录</h2>
          {(data.genetic_perturbations || []).length ? (
            <table><thead><tr><th>pert_id</th><th>类型</th><th>签名数</th></tr></thead>
              <tbody>{data.genetic_perturbations.map((g: any) => (
                <tr key={g.pert_id}><td className="mono small">{g.pert_id}</td>
                  <td>{g.pert_type}</td><td>{g.n_sigs}</td></tr>))}</tbody></table>
          ) : <div className="muted small">无匹配的遗传扰动</div>}
        </div>
        <div className="card"><h2>模拟该基因敲除的化合物</h2>
          <div className="scroll" style={{ maxHeight: 360 }}>
            <table><thead><tr><th>#</th><th>化合物</th><th>相似度</th></tr></thead>
              <tbody>{(data.mimicking_compounds || []).map((c: any, i: number) => (
                <tr key={c.pert_id}><td>{i + 1}</td>
                  <td><Link href={`/compound/?id=${encodeURIComponent(c.pert_id)}`}>{c.pert_iname || c.pert_id}</Link></td>
                  <td>{Number(c.similarity).toFixed(3)}</td></tr>))}</tbody></table>
          </div>
        </div>
      </div>
    </>
  );
}
