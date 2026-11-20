"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import TargetView from "@/components/TargetView";

export default function TargetIndex() {
  const [gene, setGene] = useState("TGFBR1");
  const [active, setActive] = useState("");
  const router = useRouter();

  useEffect(() => {
    const sync = () => {
      const sym = new URLSearchParams(window.location.search).get("symbol") || "";
      setActive(sym);
      if (sym) setGene(sym);
    };
    sync();
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  function go(sym: string) {
    const clean = sym.trim();
    if (!clean) return;
    setActive(clean);
    router.push(`/target/?symbol=${encodeURIComponent(clean)}`);
  }

  return (
    <>
      <div className="page-head"><h1>靶基因与遗传印证</h1></div>
      <div className="sub">查询靶点在肾单位各区室的表达、直接靶向药物，以及与其敲低签名高度模拟的化合物。</div>
      <div className="card" style={{ maxWidth: 640, marginBottom: 16 }}>
        <label>基因符号</label>
        <div className="row">
          <input type="text" value={gene} onChange={(e) => setGene(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") go(gene); }} />
          <button onClick={() => go(gene)}>查询</button>
        </div>
        <div className="row small" style={{ marginTop: 12, gap: 8 }}>
          {["TGFBR1", "APOL1", "HAVCR1", "JAK2", "SMAD3", "NPHS1", "PPARA"].map((g) => (
            <button key={g} className="badge grey" style={{ cursor: "pointer", border: "none" }}
              onClick={() => go(g)}>{g}</button>
          ))}
        </div>
      </div>
      {active ? <TargetView symbol={active} /> : null}
    </>
  );
}
