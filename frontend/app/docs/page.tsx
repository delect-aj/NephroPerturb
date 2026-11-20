export default function DocsPage() {
  return (
    <>
      <div className="page-head"><h1>API 与 MCP 文档</h1></div>
      <div className="sub">所有计算由确定性后端执行；LLM 仅用于自然语言参数映射，可完全关闭。</div>

      <div className="card">
        <h2>REST 端点</h2>
        <table><thead><tr><th>端点</th><th>方法</th><th>说明</th></tr></thead><tbody>
          {[
            ["/api/v1/query/signature", "POST", "签名逆转 + RTPS 排序"],
            ["/api/v1/query/pathway-tf", "POST", "按通路/TF 方向寻药"],
            ["/api/v1/compound/{id}", "GET", "化合物肾脏画像"],
            ["/api/v1/compound/{id}/explain", "GET", "T-DIKI v2 归因（结构专家贡献 + 肾上皮毒理）"],
            ["/api/v1/target/{symbol}", "GET", "靶点表达、靶向药与遗传印证"],
            ["/api/v1/similarity/structure", "POST", "结构相似与 MoA 邻域"],
            ["/api/v1/cases", "GET", "真实 GEO 肾活检队列案例（含 provenance）"],
            ["/api/v1/agent/route", "POST", "SOP 意图与参数映射"],
            ["/api/v1/agent/summarize", "POST", "结果表忠实总结"],
            ["/api/v1/downloads", "GET", "下载清单与校验和"],
          ].map(([p, m, d]) => (
            <tr key={p}><td className="mono small">{p}</td><td>{m}</td><td>{d}</td></tr>))}
        </tbody></table>
        <h2 style={{ marginTop: 18 }}>示例</h2>
        <pre className="pre">{`curl -X POST http://<host>:8091/api/v1/query/signature \\
  -H "Content-Type: application/json" \\
  -d '{"up_genes":["COL1A1","TGFB1"],"down_genes":["NPHS1","PPARA"],"top_k":20}'`}</pre>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>MCP Server</h2>
        <p className="small muted">以 Streamable HTTP 暴露 6 个工具，供 Claude / Cursor / Python Agent 接入。</p>
        <pre className="pre">{`# 启动
NEPHRO_MCP_TRANSPORT=streamable-http NEPHRO_MCP_PORT=8092 deploy/run_mcp.sh

# 客户端配置（Claude Desktop / 任意 MCP 客户端）
{
  "mcpServers": {
    "nephroperturb": { "url": "http://<host>:8092/mcp" }
  }
}`}</pre>
        <table style={{ marginTop: 10 }}><thead><tr><th>工具</th><th>用途</th></tr></thead><tbody>
          {[
            ["nephro_query_signature", "多尺度签名逆转与安全重排"],
            ["nephro_profile_compound", "化合物肾脏画像与肾毒风险"],
            ["nephro_query_pathway_tf", "通路/TF 组合检索"],
            ["nephro_target_mimicry", "基因敲除模拟化合物"],
            ["nephro_infer_moa", "SMILES / BRD 的 MoA 推断"],
            ["nephro_list_renal_cases", "真实 GEO 肾病验证队列"],
          ].map(([a, b]) => <tr key={a}><td className="mono small">{a}</td><td>{b}</td></tr>)}
        </tbody></table>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <h2>复现与 provenance</h2>
        <p className="small">
          每次检索返回 <span className="mono">job_id</span> 与 <span className="mono">provenance</span>
          （输入哈希、参数、矩阵版本、时间戳），并写入 <span className="mono">job_provenance</span> 表。
          无 <span className="mono">DEEPSEEK_API_KEY</span> 时所有功能自动运行在 0-LLM 模式；
          LLM 摘要须通过全实体 + 全数值一致性核验，未通过即回退为确定性模板（verified=false 记录原因）。
        </p>
      </div>
    </>
  );
}
