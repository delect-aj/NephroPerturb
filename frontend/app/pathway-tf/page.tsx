"use client";
import { useState } from "react";
import Link from "next/link";

export default function PathwayTF() {
  const [rows, setRows] = useState<{ name: string; dir: number }[]>([
    { name: "SMAD3", dir: -1 }, { name: "PPARA", dir: 1 },
  ]);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function run() {
    setLoading(true); setError("");
    try {
      const targets: Record<string, number> = {};
      rows.forEach((r) => { if (r.name.trim()) targets[r.name.trim()] = r.dir; });
      const res = await fetch("/api/v1/query/pathway-tf", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ targets, top_k: 30 }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || "query failed");
      setData(body);
    } catch (e: any) { setError(String(e.message || e)); }
    finally { setLoading(false); }
  }

  return (
    <>
      <div className="page-head"><h1>通路与转录因子寻药</h1></div>
      <div className="sub">按期望调控方向检索预计算的功能活性矩阵（PROGENy / CollecTRI / 肾病模块）。</div>

      <div className="card">
        <h2>目标组合</h2>
        {rows.map((row, i) => (
          <div className="row" key={i} style={{ marginBottom: 8 }}>
            <input type="text" value={row.name} placeholder="通路或 TF，如 TGFb / SMAD3 / NFKB1"
              onChange={(e) => setRows(rows.map((r, j) => j === i ? { ...r, name: e.target.value } : r))} />
            <select value={row.dir} style={{ width: 120 }}
              onChange={(e) => setRows(rows.map((r, j) => j === i ? { ...r, dir: Number(e.target.value) } : r))}>
              <option value={1}>激活 +1</option>
              <option value={-1}>抑制 −1</option>
            </select>
            <button className="ghost" onClick={() => setRows(rows.filter((_, j) => j !== i))}>删除</button>
          </div>
        ))}
        <div className="row" style={{ marginTop: 10 }}>
          <button className="ghost" onClick={() => setRows([...rows, { name: "", dir: -1 }])}>添加目标</button>
          <button onClick={run} disabled={loading}>{loading ? "检索中…" : "检索候选药物"}</button>
        </div>
        {error && <div className="small" style={{ color: "var(--bad)", marginTop: 8 }}>{error}</div>}
      </div>

      {data && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="row"><h2 style={{ margin: 0 }}>候选药物</h2><span className="spacer" />
            <span className="small muted">命中 {data.used?.length} / 未识别 {(data.missing || []).join(", ") || "无"}</span></div>
          <div className="scroll" style={{ marginTop: 10 }}>
            <table><thead><tr><th>#</th><th>化合物</th><th>评分</th><th>分期</th><th>T-DIKI</th></tr></thead>
              <tbody>{(data.results || []).map((r: any, i: number) => (
                <tr key={r.pert_id}><td>{i + 1}</td>
                  <td><Link href={`/compound/${r.pert_id}`}>{r.pert_iname || r.pert_id}</Link></td>
                  <td>{Number(r.pathway_tf_score).toFixed(2)}</td>
                  <td className="small">{r.clinical_phase || "—"}</td>
                  <td><span className={`badge ${r.tdiki_tier === "High" ? "red" : r.tdiki_tier === "Moderate" ? "amber" : "green"}`}>
                    {r.tdiki_tier || "NA"}</span></td></tr>))}</tbody></table>
          </div>
        </div>
      )}
    </>
  );
}
