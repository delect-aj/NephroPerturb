"use client";
import { useEffect, useState } from "react";
import { apiJson } from "@/lib/api";

export default function DownloadsPage() {
  const [items, setItems] = useState<any[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    apiJson("/api/v1/downloads")
      .then((d) => setItems(d.downloads || []))
      .catch((e) => setError(String(e.message || e)));
  }, []);

  return (
    <>
      <div className="page-head">
        <h1>Downloads</h1>
      </div>
      <div className="sub">
        Standardized GMT signature sets with SHA-256 checksums and matrix provenance.
      </div>
      {error && (
        <div
          className="card"
          style={{ marginBottom: 12, color: "var(--bad)", borderColor: "#fca5a5" }}
        >
          Failed to load download manifest: {error}
        </div>
      )}
      <div className="split-aside">
        <div className="card">
          <h2>Release &amp; Provenance</h2>
          <div className="kv">
            <div>Matrix version</div>
            <div>kprl-2026.11</div>
            <div>LINCS sources</div>
            <div>GSE92742 + GSE70138</div>
            <div>Gene space</div>
            <div>12,328 (978 LM / 10,174 BING)</div>
            <div>Compounds</div>
            <div>21,299 (9,888 IK-14 scaffolds)</div>
            <div>Citation</div>
            <div>NephroPerturb, 2026</div>
          </div>
        </div>

        <div className="card">
          <h2>GMT Signature Archives ({items.length})</h2>
          <table>
            <thead>
              <tr>
                <th>File</th>
                <th>Size</th>
                <th>SHA-256</th>
                <th>Link</th>
              </tr>
            </thead>
            <tbody>
              {items.map((f) => (
                <tr key={f.file}>
                  <td className="mono small">{f.file}</td>
                  <td>{(f.bytes / 1e6).toFixed(1)} MB</td>
                  <td className="mono small">{String(f.sha256).slice(0, 20)}…</td>
                  <td>
                    <a href={f.url}>Download</a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
