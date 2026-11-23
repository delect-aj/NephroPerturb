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
        Standardized GMT signature sets with SHA256 checksums and matrix provenance metadata.
      </div>
      {error && (
        <div
          className="card"
          style={{ marginBottom: 16, color: "var(--bad)", borderColor: "#fca5a5" }}
        >
          Failed to load download manifest: {error}
        </div>
      )}
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>File</th>
              <th>Size</th>
              <th>SHA256</th>
              <th>Download</th>
            </tr>
          </thead>
          <tbody>
            {items.map((f) => (
              <tr key={f.file}>
                <td className="mono small">{f.file}</td>
                <td>{(f.bytes / 1e6).toFixed(1)} MB</td>
                <td className="mono small">{String(f.sha256).slice(0, 24)}…</td>
                <td>
                  <a href={f.url}>Download</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <h2>Release & Citation</h2>
        <div className="kv">
          <div>Matrix version</div>
          <div>kprl-2026.11 (LINCS Level-5 GSE92742 + GSE70138)</div>
          <div>Gene space</div>
          <div>12,328 (978 Landmark / 10,174 BING)</div>
          <div>Compounds</div>
          <div>21,299 (9,888 unique InChIKey-14 scaffolds)</div>
          <div>Citation</div>
          <div>NephroPerturb, 2026</div>
        </div>
      </div>
    </>
  );
}
