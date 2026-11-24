"use client";
import { useEffect, useState } from "react";
import CompoundView from "@/components/CompoundView";
import { COMPOUND_PRESETS } from "@/lib/examples";

export default function CompoundIndexPage() {
  const [query, setQuery] = useState("dexamethasone");
  const [active, setActive] = useState("");

  useEffect(() => {
    const sync = () => {
      const q = (new URLSearchParams(window.location.search).get("id") || "dexamethasone").trim();
      setActive(q);
      setQuery(q);
    };
    sync();
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  function go(tok: string) {
    const clean = tok.trim();
    if (!clean) return;
    setActive(clean);
    setQuery(clean);
    const nextUrl = `/compound/?id=${encodeURIComponent(clean)}`;
    if (window.location.pathname + window.location.search !== nextUrl) {
      window.history.pushState(null, "", nextUrl);
    }
  }

  return (
    <>
      <div className="page-head">
        <h1>Compound Explorer</h1>
      </div>
      <div className="sub">
        2D structure, K-PRL signature, T-DIKI v2 risk attribution, and scaffold siblings.
      </div>
      <div className="card" style={{ marginBottom: 14 }}>
        <div className="row">
          <input
            type="text"
            style={{ flex: 1, minWidth: 220 }}
            value={query}
            placeholder="Compound name, BRD ID, or InChIKey (e.g. dexamethasone, BRD-A10188456)"
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                go(query);
              }
            }}
          />
          <button type="button" onClick={() => go(query)}>
            Search
          </button>
          <div className="chip-row">
            {COMPOUND_PRESETS.map((c) => (
              <button
                key={c}
                type="button"
                className={`chip ${active.toLowerCase() === c.toLowerCase() ? "active" : ""}`}
                onClick={() => go(c)}
              >
                {c}
              </button>
            ))}
          </div>
        </div>
      </div>
      {active ? <CompoundView id={active} onSelectCompound={go} /> : null}
    </>
  );
}
