export default function DocsPage() {
  return (
    <>
      <div className="page-head">
        <h1>API &amp; MCP Docs</h1>
        <span className="badge blue">v1.1.2</span>
      </div>
      <div className="sub">
        Deterministic REST endpoints and Streamable HTTP MCP tools. Optional LLM parsing is limited to slot extraction with zero ungrounded generation.
      </div>

      <div className="grid cols-2">
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
                ["/api/v1/agent/run", "POST", "Deterministic SOP executor: route -> resolve -> tool -> summary"],
                ["/api/v1/agent/route", "POST", "SOP intent & parameter extraction"],
                ["/api/v1/agent/summarize", "POST", "Entity/number-verified summary builder"],
                ["/api/v1/query/signature", "POST", "Multi-scale gene-signature reversal (RTPS)"],
                ["/api/v1/query/pathway-tf", "POST", "Pathway / TF / renal module search"],
                ["/api/v1/compound/{id}", "GET", "Compound kidney profile & K-PRL signature"],
                ["/api/v1/compound/{id}/explain", "GET", "T-DIKI v2 attribution"],
                ["/api/v1/target/{symbol}", "GET", "Target expression, drugs & mimicry"],
                ["/api/v1/similarity/structure", "POST", "ECFP4 Tanimoto search & MoA neighbors"],
                ["/api/v1/cases", "GET", "QC-validated GEO renal cohorts"],
                ["/api/v1/downloads", "GET", "GMT download manifest & SHA-256"],
              ].map(([p, m, d]) => (
                <tr key={p}>
                  <td className="mono small">{p}</td>
                  <td>
                    <span className="badge grey mono">{m}</span>
                  </td>
                  <td className="small">{d}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card">
          <h2>Quick cURL &amp; MCP Config</h2>
          <pre className="pre">{`# Deterministic Agent (0-LLM rules)
curl -X POST http://<host>:8091/api/v1/agent/run \\
  -H "Content-Type: application/json" \\
  -d '{"text":"Find reversal drugs for the DKD glomeruli case","use_llm":false}'

# Signature reversal query
curl -X POST http://<host>:8091/api/v1/query/signature \\
  -H "Content-Type: application/json" \\
  -d '{"up_genes":["COL1A1","TGFB1"],"down_genes":["NPHS1","PPARA"],"top_k":20}'

# MCP Streamable HTTP (Lite :8091/mcp | Standalone :8092/mcp)
{
  "mcpServers": {
    "nephroperturb": { "url": "http://<host>:8091/mcp" }
  }
}`}</pre>
          <p className="small muted" style={{ marginTop: 8 }}>
            Every run returns a <span className="mono">job_id</span> and <span className="mono">provenance</span> hash archived in SQLite <span className="mono">job_provenance</span>.
          </p>
        </div>
      </div>

      <div className="grid cols-2" style={{ marginTop: 12 }}>
        <div className="card">
          <h2>Deterministic Agent SOP Rules</h2>
          <table>
            <thead>
              <tr>
                <th>SOP</th>
                <th>Trigger Keywords</th>
                <th>MCP Tool</th>
                <th>Example Prompt</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["SOP-1", "up:, down:, signature, approved, low risk", "nephro_query_signature", "Up: COL1A1 FN1 TGFB1; Down: NPHS1 PPARA"],
                ["SOP-2", "profile, safety, nephrotoxic, MoA", "nephro_profile_compound", "Is tacrolimus nephrotoxic?"],
                ["SOP-3", "pathway, signaling, TF, inhibit, activate", "nephro_query_pathway_tf", "Inhibit SMAD3 and TGFb, activate PPARA"],
                ["SOP-4", "target, knockout, knockdown, mimic, CRISPR", "nephro_target_mimicry", "Which compounds mimic knockdown of TGFBR1?"],
                ["SOP-5", "SMILES, similar, structure, analog, BRD-", "nephro_infer_moa", "Find compounds structurally similar to CC(=O)OC1=CC=CC=C1C(=O)O"],
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

        <div className="card">
          <h2>MCP Tool Inventory</h2>
          <table>
            <thead>
              <tr>
                <th>Tool Name</th>
                <th>Capability</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["nephro_query_signature", "Multi-scale signature reversal + NephroSafe re-ranking"],
                ["nephro_profile_compound", "Compound kidney profile and T-DIKI / DIRIL risk"],
                ["nephro_query_pathway_tf", "Pathway / TF / renal module combination screen"],
                ["nephro_target_mimicry", "Compounds mimicking genetic knockdown of a target"],
                ["nephro_infer_moa", "ECFP4 structural neighbor MoA inference"],
                ["nephro_list_renal_cases", "Curated GEO human kidney biopsy cohorts"],
              ].map(([a, b]) => (
                <tr key={a}>
                  <td className="mono small">{a}</td>
                  <td className="small">{b}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}
