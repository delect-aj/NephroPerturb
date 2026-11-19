"use client";
import { useEffect, useState } from "react";

export default function DownloadsPage() {
  const [items, setItems] = useState<any[]>([]);
  useEffect(() => {
    fetch("/api/v1/downloads").then((r) => r.json())
      .then((d) => setItems(d.downloads || [])).catch(() => {});
  }, []);
  return (
    <>
      <div className="page-head"><h1>下载中心</h1></div>
      <div className="sub">标准化 GMT / 连续矩阵 / 注释表，附带 SHA256 校验和与版本信息。</div>
      <div className="card">
        <table><thead><tr><th>文件</th><th>大小</th><th>SHA256</th><th></th></tr></thead>
          <tbody>{items.map((f) => (
            <tr key={f.file}>
              <td className="mono small">{f.file}</td>
              <td>{(f.bytes / 1e6).toFixed(1)} MB</td>
              <td className="mono small">{String(f.sha256).slice(0, 24)}…</td>
              <td><a href={f.url}>下载</a></td>
            </tr>))}</tbody></table>
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <h2>版本与引用</h2>
        <div className="kv">
          <div>矩阵版本</div><div>kprl-2026.11（Level 5 GSE92742 + GSE70138）</div>
          <div>基因空间</div><div>12,328（978 Landmark / 10,174 BING）</div>
          <div>化合物</div><div>21,299（9,888 InChIKey-14 母核）</div>
          <div>引用</div><div>NephroPerturb, 2026（准备中）</div>
        </div>
      </div>
    </>
  );
}
