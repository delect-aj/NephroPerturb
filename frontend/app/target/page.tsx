"use client";
import { useEffect, useState } from "react";
import TargetView from "@/components/TargetView";

const TARGET_PRESETS = ["TGFBR1", "APOL1", "HAVCR1", "JAK2", "SMAD3", "NPHS1", "PPARA"];

export default function TargetIndex() {
  const [gene, setGene] = useState("TGFBR1");
  const [active, setActive] = useState("");

  useEffect(() => {
    const sync = () => {
      const sym = (new URLSearchParams(window.location.search).get("symbol") || "TGFBR1").trim();
      setActive(sym);
      setGene(sym);
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
    const nextUrl = `/target/?symbol=${encodeURIComponent(clean)}`;
    if (window.location.pathname + window.location.search !== nextUrl) {
      window.history.pushState(null, "", nextUrl);
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>Target &amp; Genetics</h1>
      </div>
      <div className="sub">
        Nephron compartment expression, direct targeting drugs, and genetic knockdown mimicry.
      </div>
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="row">
          <input
            type="text"
            style={{ flex: 1, minWidth: 200 }}
            value={gene}
            placeholder="Human gene symbol (e.g. TGFBR1, APOL1, HAVCR1)"
            onChange={(e) => setGene(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                go(gene);
              }
            }}
          />
          <button type="button" onClick={() => go(gene)}>
            Search
          </button>
          <div className="chip-row">
            {TARGET_PRESETS.map((g) => (
              <button
                key={g}
                type="button"
                className={`chip ${active.toUpperCase() === g ? "active" : ""}`}
                onClick={() => go(g)}
              >
                {g}
              </button>
            ))}
          </div>
        </div>
      </div>
      {active ? <TargetView symbol={active} /> : null}
    </>
  );
}
