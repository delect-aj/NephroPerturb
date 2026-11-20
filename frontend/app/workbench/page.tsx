"use client";
import { useMemo, useState } from "react";
import Link from "next/link";
import Chart from "@/components/Chart";

const PRESET = {
  up: "COL1A1\nCOL3A1\nFN1\nTGFB1\nSERPINE1\nLCN2\nHAVCR1\nSPP1",
  down: "NPHS1\nNPHS2\nPODXL\nWT1\nPPARA\nPPARGC1A\nCPT1A",
};

function tierBadge(tier?: string | null) {
  if (!tier) return <span className="badge grey">NA</span>;
  const cls = tier === "High" ? "red" : tier === "Moderate" ? "amber" : "green";
  return <span className={`badge ${cls}`}>{tier}</span>;
}

export default function Workbench() {
  const [up, setUp] = useState(PRESET.up);
  const [down, setDown] = useState(PRESET.down);
  const [context, setContext] = useState("kprl");
  const [tier, setTier] = useState("all");
  const [compartment, setCompartment] = useState("whole_kidney");
  const [approvedOnly, setApprovedOnly] = useState(false);
  const [collapse, setCollapse] = useState(true);
  const [maxDiki, setMaxDiki] = useState("");
  const [w1, setW1] = useState(1.0);
  const [w2, setW2] = useState(0.5);
  const [w3, setW3] = useState(0.2);
  const [w4, setW4] = useState(0.2);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<any>(null);
  const [selected, setSelected] = useState<any>(null);
  const [error, setError] = useState("");

  const parseGenes = (s: string) =>
    s.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean);

  async function run() {
    setLoading(true); setError(""); setSelected(null);
    try {
      const res = await fetch("/api/v1/query/signature", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          up_genes: parseGenes(up), down_genes: parseGenes(down),
          context, gene_tier: tier, kidney_compartment: compartment,
          weights: { w1, w2, w3, w4 },
          filters: {
            approved_only: approvedOnly, collapse_scaffold: collapse,
            ...(maxDiki ? { max_diki_tier: maxDiki } : {}),
          },
          top_k: 50,
        }),
      });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.detail || "query failed");
      setData(payload);
      setSelected(payload.results?.[0] || null);
    } catch (err: any) { setError(String(err.message || err)); }
    finally { setLoading(false); }
  }

  function exportJson() {
    if (!data) return;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `nephroperturb_${data.job_id || "result"}.json`; a.click();
    URL.revokeObjectURL(url);
  }

  const radar = useMemo(() => {
    if (!selected) return null;
    const vals = ["xsum", "zhang", "wtcs", "func"].map((m) =>
      Math.abs(Number(selected[`tau_${m}`] || 0)));
    return {
      radar: {
        indicator: ["XSum", "Zhang", "WTCS", "Func"].map((name) => ({ name, max: 100 })),
        radius: "62%", splitNumber: 4,
      },
      series: [{
        type: "radar", data: [{ value: vals, name: selected.pert_iname || selected.pert_id,
          areaStyle: { opacity: 0.25 }, lineStyle: { color: "#0f6cbd" },
          itemStyle: { color: "#0f6cbd" } }],
      }],
      tooltip: {},
    };
  }, [selected]);

  return (
    <>
      <div className="page-head"><h1>签名逆转工作台</h1></div>
      <div className="sub">输入疾病上/下调基因，按 K-PRL 上下文、多尺度匹配与肾毒护栏排序候选药物。</div>

      <div className="grid cols-2">
        <div className="card">
          <h2>疾病签名</h2>
          <label>上调基因（每行或逗号分隔）</label>
          <textarea value={up} onChange={(e) => setUp(e.target.value)} />
          <label>下调基因</label>
          <textarea value={down} onChange={(e) => setDown(e.target.value)} />
          <div className="row" style={{ marginTop: 12 }}>
            <button onClick={run} disabled={loading}>{loading ? "计算中…" : "运行逆转检索"}</button>
            {data && <button className="ghost" onClick={exportJson}>导出结果 + provenance</button>}
          </div>
          {error && <div className="small" style={{ color: "var(--bad)", marginTop: 8 }}>{error}</div>}
        </div>

        <div className="card">
          <h2>参数</h2>
          <div className="grid cols-2">
            <div>
              <label>扰动上下文</label>
              <select value={context} onChange={(e) => setContext(e.target.value)}>
                <option value="kprl">K-PRL（肾脏收缩，通用）</option>
                <option value="pan">Pan-Cell 全局（系统药效）</option>
                <option value="renal_epi">HA1E 肾上皮（小管损伤/纤维化）</option>
                <option value="renal_endo">血管内皮（肾小球/血管病变）</option>
                <option value="renal_immune">免疫炎症（LN/IgAN 免疫性肾病）</option>
              </select>
            </div>
            <div>
              <label>基因置信层</label>
              <select value={tier} onChange={(e) => setTier(e.target.value)}>
                <option value="all">全部 12,328</option>
                <option value="bing">BING 高置信</option>
                <option value="lm">仅 Landmark 978</option>
              </select>
            </div>
            <div>
              <label>目标肾区室</label>
              <select value={compartment} onChange={(e) => setCompartment(e.target.value)}>
                {["whole_kidney", "glomerulus", "podocyte", "pt", "tal", "dct", "cd", "endo", "immune", "tubule"]
                  .map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div>
              <label>最高 T-DIKI 风险</label>
              <select value={maxDiki} onChange={(e) => setMaxDiki(e.target.value)}>
                <option value="">不限</option>
                <option value="Moderate">≤ Moderate</option>
                <option value="Low">仅 Low</option>
              </select>
            </div>
          </div>
          <div className="row" style={{ marginTop: 8 }}>
            <label style={{ margin: 0 }}><input type="checkbox" checked={approvedOnly}
              onChange={(e) => setApprovedOnly(e.target.checked)} /> 仅已批准药物</label>
            <label style={{ margin: 0 }}><input type="checkbox" checked={collapse}
              onChange={(e) => setCollapse(e.target.checked)} /> 按母核折叠</label>
          </div>
          <h2 style={{ marginTop: 18 }}>四维权重</h2>
          {[["疗效 RenalConn", w1, setW1], ["肾毒风险惩罚", w2, setW2],
            ["靶点区室表达", w3, setW3], ["遗传印证", w4, setW4]].map(([label, val, set]: any) => (
            <div key={label}>
              <label>{label}: {Number(val).toFixed(2)}</label>
              <input type="range" min={0} max={2} step={0.05} value={val}
                onChange={(e) => set(Number(e.target.value))} style={{ width: "100%" }} />
            </div>
          ))}
        </div>
      </div>

      {data && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="row">
            <h2 style={{ margin: 0 }}>候选药物（{data.results?.length || 0}）</h2>
            <span className="spacer" />
            <span className="small muted mono">job {data.job_id}</span>
          </div>
          <div className="scroll" style={{ marginTop: 10 }}>
            <table>
              <thead><tr>
                <th>#</th><th>化合物</th><th>分期</th><th>RTPS</th><th>RenalConn</th>
                <th>τ XSum</th><th>τ Zhang</th><th>τ WTCS</th><th>τ Func</th>
                <th>DIKI</th><th>DIRIL</th><th>提示</th>
              </tr></thead>
              <tbody>
                {(data.results || []).map((r: any, i: number) => (
                  <tr key={r.pert_id} onClick={() => setSelected(r)} style={{ cursor: "pointer" }}>
                    <td>{i + 1}</td>
                    <td><Link href={`/compound/${r.pert_id}`} onClick={(e) => e.stopPropagation()}>
                      {r.pert_iname || r.pert_id}</Link>
                      <div className="small muted mono">{r.pert_id}</div></td>
                    <td className="small">{r.clinical_phase || "—"}</td>
                    <td>{Number(r.rtps).toFixed(1)}</td>
                    <td>{Number(r.renalconn).toFixed(1)}</td>
                    {["xsum", "zhang", "wtcs", "func"].map((m) => (
                      <td key={m}>{Number(r[`tau_${m}`] || 0).toFixed(0)}</td>
                    ))}
                    <td>{tierBadge(r.tdiki_tier)}</td>
                    <td>{r.diril_label === 1 ? <span className="badge red">阳性</span>
                      : r.diril_label === 0 ? <span className="badge green">阴性</span>
                        : <span className="badge grey">-</span>}</td>
                    <td className="small">{r.moa ? String(r.moa).split("|")[0] : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {selected && radar && (
        <div className="grid cols-2" style={{ marginTop: 16 }}>
          <div className="card">
            <h2>分项 τ 画像 · {selected.pert_iname || selected.pert_id}</h2>
            <Chart option={radar} />
          </div>
          <div className="card">
            <h2>结果溯源</h2>
            <div className="kv">
              <div>输入哈希</div><div className="mono small">{data.provenance?.input_hash?.slice(0, 32)}…</div>
              <div>可解析基因</div><div>up {data.provenance?.n_up} / down {data.provenance?.n_down}</div>
              <div>矩阵版本</div><div>{data.provenance?.matrix_version}</div>
              <div>生成时间</div><div className="small">{data.provenance?.generated_at}</div>
              <div>未识别</div><div className="small">{[
                ...(data.provenance?.missing_up || []),
                ...(data.provenance?.missing_down || [])].join(", ") || "无"}</div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
