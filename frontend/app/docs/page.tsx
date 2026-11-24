export default function DocsPage() {
  return (
    <>
      <div className="page-head">
        <h1>API &amp; MCP Docs</h1>
        <span className="badge blue">v1.2.2</span>
      </div>
      <div className="sub">
        Skill-guided DeepSeek ReAct agent with Title/Abstract Europe PMC &amp; PubMed search, cohesive 4-section synthesis reports, auto-verified References, SSE streaming, and 9 MCP tools.
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
                ["/api/v1/agent/stream", "POST", "SSE multi-turn ReAct / deterministic multi-step research stream"],
                ["/api/v1/agent/status", "GET", "Server LLM readiness, rolling IP hourly quota & provider info"],
                ["/api/v1/agent/skills", "GET", "List the 6 declarative SKILL.md playbooks & execution policy"],
                ["/api/v1/agent/session/{id}", "GET/DELETE", "Inspect or reset multi-turn research session ledger"],
                ["/api/v1/agent/run", "POST", "Legacy single-turn deterministic SOP executor"],
                ["/api/v1/literature/search", "POST", "Bidirectional kidney efficacy & nephrotoxicity literature + trials"],
                ["/api/v1/compounds/compare", "POST", "Head-to-head comparison (2-4 compounds) on safety & renal modules"],
                ["/api/v1/query/signature", "POST", "Multi-scale gene-signature reversal (RTPS)"],
                ["/api/v1/query/pathway-tf", "POST", "Pathway / TF / renal module search"],
                ["/api/v1/compound/{id}", "GET", "Compound kidney profile & K-PRL signature"],
                ["/api/v1/compound/{id}/explain", "GET", "T-DIKI v2 attribution"],
                ["/api/v1/target/{symbol}", "GET", "Target expression, drugs & knockdown mimicry"],
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
          <h2>Execution Policy, Guardrails &amp; MCP</h2>
          <pre className="pre">{`# SSE Research Stream (Auto DeepSeek ReAct + quota fallback)
curl -N -X POST http://<host>:8091/api/v1/agent/stream \\
  -H "Content-Type: application/json" \\
  -d '{"text":"Find DKD reversal drugs & check literature","mode":"auto"}'

# Bidirectional Literature & ClinicalTrials Search
curl -X POST http://<host>:8091/api/v1/literature/search \\
  -H "Content-Type: application/json" \\
  -d '{"entity":"dexamethasone","disease_context":"DKD"}'

# MCP Streamable HTTP (9 tools on :8091/mcp)
{
  "mcpServers": {
    "nephroperturb": { "url": "http://<host>:8091/mcp" }
  }
}`}</pre>
          <ul className="small muted" style={{ paddingLeft: 18, marginTop: 8 }}>
            <li><strong>Reproducibility</strong>: DeepSeek pinned at <code>temperature=0.0</code>, <code>seed=42</code>, and scoped strictly per Skill tool allowlist.</li>
            <li><strong>Zero Hallucination</strong>: Automated verification cross-checks every reported PMID, NCT identifier, compound ID, and score against retrieved source records.</li>
            <li><strong>Rate Limiting</strong>: Public visitors share configurable rolling hourly per-IP &amp; daily caps (auto-degrades to rule-based fast mode when reached).</li>
          </ul>
        </div>
      </div>

      <div className="grid cols-2" style={{ marginTop: 12 }}>
        <div className="card">
          <h2>6 Modular Agent Skills</h2>
          <table>
            <thead>
              <tr>
                <th>Skill ID</th>
                <th>Steps</th>
                <th>Allowed Tools &amp; Playbook</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["disease-repurposing", "6", "Cohort/signature/pathway screen -> auto Low T-DIKI re-screen -> top-2 PubMed/trials"],
                ["toxicity-rescue", "5", "Compound profile -> T-DIKI attribution -> Low-DIKI structural analogs -> safety papers"],
                ["target-to-lead", "5", "Nephron target expression -> knockdown mimicry -> lead safety -> PubMed"],
                ["structure-moa-evidence", "4", "ECFP4 Tanimoto scan -> consensus MoA -> neighbor safety -> kidney literature"],
                ["literature-evidence", "5", "Bidirectional Europe PMC / PubMed + ClinicalTrials.gov -> Novelty & evidence tier"],
                ["compound-compare", "5", "2-4 compound matrix (T-DIKI, PROGENy, 9 renal modules) + trials/papers"],
              ].map(([id, st, desc]) => (
                <tr key={id}>
                  <td className="mono small">{id}</td>
                  <td className="mono small">{st}</td>
                  <td className="small">{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="card">
          <h2>MCP Tool Inventory (9 Tools)</h2>
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
                ["nephro_search_literature", "Bidirectional Europe PMC / PubMed efficacy + nephrotoxicity search"],
                ["nephro_search_clinical_trials", "ClinicalTrials.gov v2 kidney study lookup"],
                ["nephro_compare_compounds", "Head-to-head renal pathway, module & safety comparison"],
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
