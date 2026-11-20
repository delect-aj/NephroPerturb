"use client";
import { useEffect, useState } from "react";
import Link from "next/link";

const STATS = [
  ["21,299", "小分子化合物"],
  ["12,328", "L1000 基因"],
  ["591,697", "Level-5 签名"],
  ["9,888", "InChIKey-14 母核"],
  ["31,082", "遗传/配体扰动"],
  ["725", "CollecTRI 转录因子"],
];

export default function Home() {
  const [cases, setCases] = useState<any[]>([]);
  const [health, setHealth] = useState<any>(null);
  useEffect(() => {
    fetch("/api/v1/cases").then((r) => r.json()).then((d) => setCases(d.cases || [])).catch(() => {});
    fetch("/health").then((r) => r.json()).then(setHealth).catch(() => {});
  }, []);

  return (
    <>
      <div className="page-head"><h1>NephroPerturb</h1>
        <span className="badge grey">{health ? "API 在线" : "连接中…"}</span></div>
      <div className="sub">
        肾脏上下文收缩扰动谱（K-PRL）× 多尺度逆转匹配 × 肾毒性安全护栏 × 确定性 Agent/MCP
      </div>

      <div className="grid cols-3" style={{ marginBottom: 16 }}>
        {STATS.map(([v, l]) => (
          <div className="card" key={l}><div className="stat">{v}</div><div className="stat-label">{l}</div></div>
        ))}
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>快速开始</h2>
          <p className="small muted">粘贴疾病上/下调基因，或直接从内置肾病案例开始。</p>
          <div className="row" style={{ marginTop: 10 }}>
            <Link href="/workbench"><button>进入签名逆转工作台</button></Link>
            <Link href="/cases"><button className="ghost">浏览案例库</button></Link>
          </div>
          <div className="row" style={{ marginTop: 16, gap: 6 }}>
            {cases.map((c) => (
              <Link key={c.case_id} href={`/cases?run=${c.case_id}`} className="badge grey">
                {c.case_id}
              </Link>
            ))}
          </div>
        </div>

        <div className="card">
          <h2>覆盖与机制</h2>
          <div className="kv">
            <div>上下文</div><div>K-PRL / Pan-Cell / HA1E 肾上皮 / 内皮 / 免疫</div>
            <div>算法</div><div>WTCS · XSum · ZhangScore · PROGENy/CollecTRI 功能匹配</div>
            <div>校准</div><div>随机基因集长度匹配的肾背景 τ</div>
            <div>安全</div><div>FDA DIRIL 金标准 + T-DIKI 双模态风险</div>
            <div>复现</div><div>每次查询生成 provenance 与 input hash</div>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>推荐入口</h2>
        <div className="grid cols-3">
          <Link href="/workbench">签名逆转工作台</Link>
          <Link href="/pathway-tf">通路与 TF 组合寻药</Link>
          <Link href="/target/?symbol=TGFBR1">靶基因与遗传印证</Link>
          <Link href="/downloads">下载 K-PRL / GMT 数据包</Link>
          <Link href="/docs">REST 与 MCP 接入文档</Link>
          <Link href="/cases">DKD / LN / IgAN / AKI / CKD 案例</Link>
        </div>
      </div>
    </>
  );
}
