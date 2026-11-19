"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

export default function TargetIndex() {
  const [gene, setGene] = useState("TGFBR1");
  const router = useRouter();
  return (
    <>
      <div className="page-head"><h1>靶基因与遗传印证</h1></div>
      <div className="sub">查询靶点在肾单位各区室的表达、直接靶向药物，以及与其敲低签名高度模拟的化合物。</div>
      <div className="card" style={{ maxWidth: 640 }}>
        <label>基因符号</label>
        <div className="row">
          <input type="text" value={gene} onChange={(e) => setGene(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && gene.trim()) router.push(`/target/${gene.trim()}`); }} />
          <button onClick={() => gene.trim() && router.push(`/target/${gene.trim()}`)}>查询</button>
        </div>
        <div className="row small" style={{ marginTop: 12, gap: 8 }}>
          {["TGFBR1", "APOL1", "HAVCR1", "JAK2", "SMAD3", "NPHS1", "PPARA"].map((g) => (
            <a key={g} className="badge grey" href={`/target/${g}`}>{g}</a>
          ))}
        </div>
      </div>
    </>
  );
}
