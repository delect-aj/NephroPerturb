"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import CompoundView from "@/components/CompoundView";
import { COMPOUND_PRESETS } from "@/lib/examples";

export default function CompoundIndexPage() {
  const [query, setQuery] = useState("dexamethasone");
  const [active, setActive] = useState("");
  const router = useRouter();

  useEffect(() => {
    const sync = () => {
      const q = new URLSearchParams(window.location.search).get("id") || "";
      setActive(q);
      if (q) setQuery(q);
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
    router.push(`/compound/?id=${encodeURIComponent(clean)}`);
  }

  return (
    <>
      <div className="page-head">
        <h1>Compound Explorer</h1>
      </div>
      <div className="sub">
        Look up any compound by name, BRD ID, or InChIKey across 21,299 LINCS perturbations and T-DIKI v2 safety annotations.
      </div>
      <div className="card" style={{ maxWidth: 680, marginBottom: 18 }}>
        <label>Compound name, BRD ID, or InChIKey</label>
        <div className="row">
          <input
            type="text"
            value={query}
            placeholder="e.g. dexamethasone, BRD-A10188456, or losartan"
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") go(query);
            }}
          />
          <button type="button" onClick={() => go(query)}>
            Search
          </button>
        </div>
        <div className="chip-row" style={{ marginTop: 12 }}>
          <span className="small muted">Examples:</span>
          {COMPOUND_PRESETS.map((c) => (
            <button key={c} type="button" className="chip" onClick={() => go(c)}>
              {c}
            </button>
          ))}
        </div>
      </div>
      {active ? <CompoundView id={active} /> : null}
    </>
  );
}
