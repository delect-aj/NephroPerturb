export default function DocsPage() {
  return (
    <>
      <div className="page-head">
        <h1>API & MCP Documentation</h1>
      </div>
      <div className="sub">
        All numerical scores and safety annotations are computed by the deterministic backend. LLM integration is restricted to optional natural-language slot extraction.
      </div>

      <div className="card">
        <h2>REST Endpoints</h2>
        <table>
          <thead>
            <tr>
              <th>Endpoint</th>
              <th>Method</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {[
              ["/api/v1/agent/run", "POST", "Deterministic SOP Agent: route -> resolve -> execute tool -> template summary"],
              ["/api/v1/agent/route", "POST", "SOP intent & parameter extraction only"],
              ["/api/v1/agent/summarize", "POST", "Entity/number-verified summary generation"],
              ["/api/v1/query/signature", "POST", "Multi-scale gene-signature reversal + RTPS ranking"],
              ["/api/v1/query/pathway-tf", "POST", "Drug search by PROGENy / CollecTRI / renal module direction"],
              ["/api/v1/compound/{id}", "GET", "Full compound kidney profile & K-PRL signature"],
              ["/api/v1/compound/{id}/explain", "GET", "T-DIKI v2 risk attribution (structure + HA1E toxicity)"],
              ["/api/v1/target/{symbol}", "GET", "Target expression, targeting drugs & knockdown mimicry"],
              ["/api/v1/similarity/structure", "POST", "ECFP4 Tanimoto structure similarity & MoA neighbors"],
              ["/api/v1/cases", "GET", "Curated GEO human kidney biopsy validation cohorts"],
              ["/api/v1/downloads", "GET", "GMT download manifest with SHA256 checksums"],
            ].map(([p, m, d]) => (
              <tr key={p}>
                <td className="mono small">{p}</td>
                <td>
                  <span className="badge grey mono">{m}</span>
                </td>
                <td>{d}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <h2 style={{ marginTop: 18 }}>Examples</h2>
        <pre className="pre">{`# Deterministic Agent runner (0-LLM rules mode)
curl -X POST http://<host>:8091/api/v1/agent/run \\
  -H "Content-Type: application/json" \\
  -d '{"text":"Find reversal drugs for the DKD glomeruli case","use_llm":false}'

# Direct signature reversal query
curl -X POST http://<host>:8091/api/v1/query/signature \\
  -H "Content-Type: application/json" \\
  -d '{"up_genes":["COL1A1","TGFB1"],"down_genes":["NPHS1","PPARA"],"top_k":20}'`}</pre>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>Deterministic Agent SOP Rules</h2>
        <p className="small muted">
          NephroAgent does not invent plans or numbers. It routes natural language deterministically across six pre-registered SOPs and invokes the corresponding backend tool.
        </p>
        <table>
          <thead>
            <tr>
              <th>SOP</th>
              <th>Trigger Keywords</th>
              <th>Tool Called</th>
              <th>Example Prompt</th>
            </tr>
          </thead>
          <tbody>
            {[
              ["SOP-1", "up:, down:, signature, approved, low nephrotoxicity", "nephro_query_signature", "Up: COL1A1 FN1 TGFB1; Down: NPHS1 PPARA"],
              ["SOP-2", "profile, safety, nephrotoxic, MoA, compound info", "nephro_profile_compound", "Is tacrolimus nephrotoxic? Show its kidney safety profile"],
              ["SOP-3", "pathway, signaling, TF, inhibit, activate, SMAD/TGFb/PPAR", "nephro_query_pathway_tf", "Inhibit SMAD3 and TGFb, activate PPARA"],
              ["SOP-4", "target, knockout, knockdown, mimic, CRISPR, shRNA", "nephro_target_mimicry", "Which compounds mimic knockdown of TGFBR1?"],
              ["SOP-5", "SMILES, similar, structure, analog, neighbor, BRD-", "nephro_infer_moa", "Find compounds structurally similar to CC(=O)OC1=CC=CC=C1C(=O)O"],
              ["SOP-6", "case, cohort, DKD, LN, IgAN, CKD, AKI", "nephro_run_renal_case", "Find reversal drugs for the DKD glomeruli case"],
            ].map(([sop, kw, tool, ex]) => (
              <tr key={sop}>
                <td>
                  <span className="badge blue">{sop}</span>
                </td>
                <td className="small">{kw}</td>
                <td className="mono small">{tool}</td>
                <td className="small mono">{ex}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>MCP Server (Streamable HTTP)</h2>
        <p className="small muted">
          Single-process Lite deployments mount MCP directly at <span className="mono">http://&lt;host&gt;:8091/mcp</span>. Standalone multi-worker deployments expose <span className="mono">http://&lt;host&gt;:8092/mcp</span>.
        </p>
        <pre className="pre">{`{
  "mcpServers": {
    "nephroperturb": {
      "url": "http://<host>:8091/mcp"
    }
  }
}`}</pre>
        <table style={{ marginTop: 10 }}>
          <thead>
            <tr>
              <th>MCP Tool</th>
              <th>Purpose</th>
            </tr>
          </thead>
          <tbody>
            {[
              ["nephro_query_signature", "Multi-scale gene-signature reversal + NephroSafe re-ranking"],
              ["nephro_profile_compound", "Compound kidney profile and T-DIKI / DIRIL risk"],
              ["nephro_query_pathway_tf", "Pathway / TF combination search"],
              ["nephro_target_mimicry", "Compounds mimicking genetic knockdown of a target"],
              ["nephro_infer_moa", "Structure-neighbor MoA inference from SMILES or BRD ID"],
              ["nephro_list_renal_cases", "Curated GEO human kidney biopsy cohorts"],
            ].map(([a, b]) => (
              <tr key={a}>
                <td className="mono small">{a}</td>
                <td>{b}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>Reproducibility & Grounded Verification</h2>
        <p className="small">
          Every query returns a unique <span className="mono">job_id</span> and{" "}
          <span className="mono">provenance</span> record (input hash, parameters, matrix version, UTC timestamp) stored in{" "}
          <span className="mono">job_provenance</span>. Without <span className="mono">DEEPSEEK_API_KEY</span>, all routes run in 0-LLM mode. Any optional LLM summary passes through an entity + number verifier and falls back to the deterministic template if any mismatch is detected.
        </p>
      </div>
    </>
  );
}
