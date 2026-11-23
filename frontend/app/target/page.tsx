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
    setGene(clean);
    router.push(`/target/?symbol=${encodeURIComponent(clean)}`);
  }

  return (
    <>
      <div className="page-head">
        <h1>Target & Genetics</h1>
      </div>
      <div className="sub">
        Inspect nephron compartment expression, direct targeting drugs, and small molecules mimicking genetic knockdown.
      </div>
      <div className="card" style={{ maxWidth: 680, marginBottom: 18 }}>
        <label>Human gene symbol</label>
        <div className="row">
          <input
            type="text"
            value={gene}
            placeholder="e.g. TGFBR1, APOL1, HAVCR1"
            onChange={(e) => setGene(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") go(gene);
            }}
          />
          <button type="button" onClick={() => go(gene)}>
            Search
          </button>
        </div>
        <div className="chip-row" style={{ marginTop: 12 }}>
          <span className="small muted">Examples:</span>
          {["TGFBR1", "APOL1", "HAVCR1", "JAK2", "SMAD3", "NPHS1", "PPARA"].map((g) => (
            <button key={g} type="button" className="chip" onClick={() => go(g)}>
              {g}
            </button>
          ))}
        </div>
      </div>
      {active ? <TargetView symbol={active} /> : null}
    </>
  );
}
