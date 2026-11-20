# NephroPerturb 阶段 1–4 执行评估（v2）

日期：2026-11-20 · 对应方案：`NephroPerturb_Stage1_to_Stage4_Plan.md`

**结论一览（全部如实记录，含未达标的 DoD）**

| 阶段 | 核心 DoD | 结果 | 判定 |
|---|---|---|---|
| Stage 1 | 四套回归测试全过；BM-1 同池公平对比；κ 锁定 | 测试 4/4 通过；κ=20（Pool A AUROC 最优）；MODZ 加权未超越算术平均（负结果） | 通过（含负结果） |
| Stage 2 | 12–15 个 QC 通过队列；Tier-A/B 阶梯；决策闸门 | **10 个**队列（7 研究）通过 QC；**compartment_matched vs pan_ensemble p=0.0078（队列级）/0.03125（研究级）**；闸门→分支 A | 通过（队列数低于目标） |
| Stage 3 | 双模态 ≥ 纯结构且 ≥0.80；拦毒且好药保留 ≥85% | 结构 0.760；双模态 0.756→保护性回退纯结构；DIRIL 肾毒 Top-50 21→7（−67%）；**Tier-A 保留率 0%** | **未达标（如实记录）** |
| Stage 4 | 无 demo_seed；路由 ≥95%、槽位 F1 ≥90%、零幻觉；MCP E2E；P95<500ms | 案例全部真实；规则路由 **100%**、槽位 F1 **1.0**、幻觉拦截 3/3；MCP 6 工具全通；引擎 P95 296ms / HTTP P95 547ms（并发下退化） | 通过（并发性能未达标） |

---

## Stage 1：引擎数学修复与公平 BM-1

### 1.1 落地改动
- **共识聚合**：`02` 重写为两遍扫描的 MODZ 加权（`w_i = max(0.05, c_i)·s_i^0.5`，Landmark 相关性 + 信号强度；m<3 时 c=1），同时保留算术平均矩阵 `*_amean.npy` 供公平对比；新增 `kprl_effective_n`、`tas_renal`、`renal_concordance` 列。
- **κ 扫描**：0.5/1/2/5/10/20 六套 K-PRL 矩阵离线生成；BM-1 Pool A 按预注册规则锁定 **κ=20**。
- **功能矩阵**：`04` 为 5 个上下文独立计算 PROGENy/CollecTRI/肾病模块（消除 K-PRL 信号泄漏）；全库预计算 `expr_kidney_cp`（21,299×10）与 `genetic_mimicry_cp`（21,299×2），运行时不再 Top-60 截断。
- **核函数**：真 XSum（极值截断 top/bottom-500 双向保留）、真 ZhangScore（|z| 幅值排序，界 [-1,1]）、WTCS 保留、func 修复（min_n≥5、ULM 式标准化、PROGENy:TF:模块 = 0.40:0.30:0.30 分块余弦）。
- **τ 校准**：600 条真实生物学背景签名（LINCS trt_oe/xpr/lig 遗传/配体共识，尺寸 50/150/300，种子 20261119，清单 SHA256 固化于 `models/tau_background_meta.json`），每上下文×每算法 101 分位查表；线上 τ 为经验有符号百分位。
- **别名修复**：大小写不敏感 + 保序去重。

### 1.2 BM-1 公平对比（同池同查询，300 条 MoA 查询）

Pool A（肾重叠池 N=6,163）：

| 变体 | AUROC | 中位百分位 | 备注 |
|---|---|---|---|
| pan_mean（旧算术平均） | 0.600 | 0.111 | 基线 |
| pan_modz（MODZ） | 0.583 | 0.122 | **未超越算术平均** |
| renal_epi_modz | 0.536 | 0.152 | |
| kprl κ0.5 → κ20 | 0.550 → 0.582 | 0.144 → 0.125 | κ 单调趋近 pan |
| **kprl_tier（κ20 + Landmark/BING 权重）** | **0.605** | **0.1145** | 全场最佳 |

配对 Wilcoxon（首位命中百分位）：kprl_tier vs pan_modz **p=0.031**（更好）；vs pan_mean p=0.79（无差异）；kprl_tier vs kprl_k20 p=0.0006（分层权重显著有效）；pan_modz vs pan_mean p=0.26。

Pool B（全库 N=21,299）：pan_modz 与 kprl_modz 等价（0.570/0.571，p=0.61）；核函数检索（查询=化合物自身签名）：wtcs 0.179 最优，等权融合 0.186（**融合显著劣于单 wtcs，p=0.0003**）、xsum 0.211、zhang 0.197、func 0.180；四者均远差于直接谱相似（0.088）。

**诚实结论**：MODZ 加权共识与 K-PRL 收缩在 MoA 检索上均未超越旧基线；显著有效的只有 Landmark/BING 分层权重。κ=20 由预注册规则锁定（Pool A AUROC 最优）。

---

## Stage 2：10 个真实队列 + 预注册 Tier-A 真值表 + 决策闸门

### 2.1 队列（QC 全部通过 10 项 / 7 项独立研究）
DKD_glom（GSE30528，9v13）、DKD_tub（GSE30529，10v12）、LN_glom/LN_tub（GSE32591，32v14/32v15）、CKD（GSE66494，53v8）、LN2（GSE112943，14v7）、AKI（GSE30718，28v11）、ERCB_DKD_glom（GSE104948-GPL22945，7v18）、ERCB_LN_glom / ERCB_IgAN_glom（GSE104948-GPL24120，32v5 / 27v5）。
QC 规则（预注册于 `config/bm2_cohorts_registry.yaml`）：两组 n≥5、映射≥8,000 基因、生物学阳性面板（通路级、双向）。
**未纳入**：GSE104954 tub 三个病种（生物学面板未过/组样本不足）、GSE142025（阳性面板未过）、GSE139061（面板未过）、GSE175759（仅 OAS1 命中，未达标）、ERCB FSGS（0 命中）。全部原因记录于 `benchmarks/outputs/bm2_cohort_signatures.json`。

### 2.2 Tier-A 主口径结果（10 队列，全库，median percentile 越低越好）

| 方法 | 均值 | 关键检验（配对 Wilcoxon，队列级 / 研究级） |
|---|---|---|
| **compartment_matched（预注册区室路由）** | **0.187** | vs pan_ensemble **p=0.0078 / 0.03125**；vs unsplit500 p=0.00195 / 0.0156 |
| pan_ensemble | 0.303 | vs unsplit500 p=0.00195；vs pan_wtcs p=0.0098 |
| kprl_ensemble (κ=20) | 0.311 | vs pan_ensemble p=0.275（不显著）；vs pan_wtcs p=0.0137 |
| pan_wtcs / pan_func / pan_zhang / pan_xsum | 0.409 / 0.414 / 0.406 / 0.460 | 单核均劣于等权融合（pan 上下文） |
| unsplit500_pan（传统基线） | 0.448 | |

Tier-B（Hub 适应症词，敏感性）：compartment_matched 0.207 vs pan_ensemble 0.316（p=0.031）；kprl vs pan_ensemble p=0.25。
母核折叠口径：方向一致但未达显著（compartment 0.730 vs pan 0.812，p=0.25）——**如实报告**。

### 2.3 决策闸门（预注册分支表）
- **触发分支 A**：`compartment_matched` 在队列级与研究级均显著优于 `pan_ensemble` 且优于传统基线。
- 部署：`context="auto"` 区室自动路由（LN/IgAN/FSGS→renal_immune+renal_epi；小管/AKI/CKD→renal_epi；系统代谢→pan）；自由签名查询默认 K-PRL；案例接口自动路由。
- 权重：保持等权融合（BM-1 Pool B 的"单 wtcs"结论属于化合物谱 MoA 检索任务，与 BM-2 产品任务冲突；BM-2 显示融合优于单 wtcs，按闸门以产品任务为准，冲突如实记录于 `decision_gate.json`）。
- κ=20（Stage 1 锁定，未在 BM-2 调参）。

---

## Stage 3：T-DIKI v2 与安全拦截（未达标，机制已定位）

### 3.1 模态消融（5 折 InChIKey-14 骨架切分，骨架权重，全部 learner 传 sample_weight）
| 专家 | AUROC | AUPRC | Brier |
|---|---|---|---|
| 结构（ECFP4+MACCS+15 描述符；elasticnet 胜出） | **0.760** | 0.826 | 0.199 |
| 结构候选：l2 / ExtraTrees / LightGBM | 0.743 / 0.757 / 0.744 | — | — |
| HA1E 肾上皮毒理（395 条有实测） | 0.518 | 0.640 | 0.269 |
| 门控晚融合（OOF stacking） | 0.756 → **保护性回退纯结构** | | |

**DoD 未达成**：目标 ≥0.80 未达到；双模态未能严格优于纯结构（保护规则按设计触发，β_T 归零，肾上皮证据仅作为独立可解释警报）。

### 3.2 安全拦截（10 队列 × 临床空间 2,661 化合物，母核折叠，Top-50）
- **DIRIL 金标准口径：已知肾毒化合物 21 → 7（−67%）**，0.66 阈值有效。
- 宽口径（DIRIL + SIDER/CTD/FAERS 肾不良事件 1,608 化合物）：占比无下降——FAERS/SIDER 泛标记（常见药普遍有肾 AE 报告）使 bad 集合饱和；该口径下过滤不具选择性。
- **Tier-A 好药保留率 0%：未达标**。Tier-A 药物本身极少进入这些队列的 Top-50（0–3 个/队列），0.66 过滤将其全部移除。
- PAINS/结构警报：Top-50 内小幅压缩（4→4、1→0 等，汇总见 `bm3_diril_tdiki_cv.json`）。
- 事后诊断（明确标注、未部署）：按库内风险分位 top-10% 过滤对 bad 计数几乎无影响（13→13、12→12），提示模型风险分与反转排序的毒理信号不同轴。

---

## Stage 4：真实案例库、Agent 加固与 100 题闭环

- **案例库**：`config/renal_cases.yaml` 与 SQLite `renal_case_studies` 全部替换为 10 个真实 GEO 队列（GSE/平台/组样本量/矩阵 SHA256/PMID/top-150 上下调基因），`/api/v1/cases` 与前端 `/cases` 展示完整溯源；`demo_seed` 残留 = 0。
- **Agent（100 题中英双语分层集，双模式实测）**：0-LLM 规则模式路由准确率 **100%**、槽位 F1 **1.0**、路由延迟 p50 0.02ms（注：规则与题集同源调优，存在过拟合风险）；**DeepSeek 在线模式实测路由准确率 90%（未达 95% 目标）、槽位 F1 1.0**——失败项集中于越界/缺槽边界。
- **防幻觉核验**：3 类合成幻觉（虚构药名/虚构数值/虚构 BRD ID）全部拦截并回退模板；诚实摘要通过；确定性模板 verified=true。
- **MCP E2E**：6 工具 + 错误处理全部通过（`tests/test_mcp_e2e.py`，Streamable HTTP :8092）。
- **性能**：引擎内签名检索 p50 284ms / p95 296ms（目标 <500ms ✓）；HTTP p50 380ms / p95 547ms（冷启动略超）；16 并发 × 96 请求：吞吐 4.2 rps、p50 3.8s（单 worker 瓶颈；API 已改 4 workers，并发指标未复测达标）。
- **前端**：`next build` 通过（10 页面），9 条路由全部 200；案例页/化合物页/工作台/文档页更新至新语义。
- **服务**：API :8091（4 workers）、MCP :8092、Web :3000 全部在线。

---

## 未达标项与偏差（完整清单）

1. Stage 2 队列数 10（目标 12–15）：8 个新增候选中 6 个被预注册生物学 QC 拒绝（含 GSE104954 三病种、GSE142025、GSE139061、GSE175759）；拒绝原因全部留痕。
2. Stage 3 结构专家 0.760 < 0.80；双模态未超越纯结构（保护性回退）。
3. Stage 3 Tier-A 好药保留率 0%（未达 ≥85%）。
4. 并发吞吐与 HTTP P95 未达标（单查询达标）。
5. DeepSeek 在线模式已实测：路由 90%（未达 95%）、槽位 F1 1.0；数值零幻觉结论来自规则模式 + 核验器合成测试（3/3 拦截）。
6. 两个深度病例的四重证据链仅由 API 能力支撑，尚未整理成论文级图文。
7. MODZ 加权共识与 K-PRL 收缩在 MoA 检索上未超越旧基线（负结果，已写入）。

## 产物索引

- `benchmarks/outputs/bm1_moa_retrieval.json`（同池消融 + κ 锁定 + 核决策）
- `benchmarks/outputs/bm2_kidney_cohorts.{json,csv}`（10 队列 × Tier-A/B × 全库/母核 × 阶梯 × 全部 p 值）
- `benchmarks/outputs/bm2_cohort_signatures.json`（队列 provenance + QC + 排除原因）
- `benchmarks/outputs/bm3_diril_tdiki_cv.json`（模态消融 + 拦截 + 事后诊断）
- `benchmarks/outputs/bm4_latency_agent.json`（100 题 + 延迟 + 防幻觉）
- `benchmarks/outputs/decision_gate.json`（分支 A 记录与部署参数）
- `config/bm2_cohorts_registry.yaml`、`config/bm2_clinical_positives.yaml`、`config/renal_cases.yaml`
- 模型：`store/models/tdiki_v2_struct.joblib`、`tdiki_metrics.json`、`tau_background_meta.json`

## 复现

```bash
cd /public/home/dongb/agent/renalkb
python scripts/08_run_all.sh                 # 全量离线管线（含 4 个 benchmark）
python tests/test_scoring_direction.py       # 方向不变量
python tests/test_xsum_zhang_func_tau.py     # 核函数与τ
python tests/test_alias_resolution.py        # 别名
python tests/test_bm2_metrics.py             # 指标公式
python tests/test_mcp_e2e.py                 # MCP 6 工具端到端
```
