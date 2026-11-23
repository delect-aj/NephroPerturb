# NephroPerturb 轻量化单核部署指南（适配 2 核 / 2 GB 内存 / 20 GB 系统盘）

> 本方案通过 **基因主序转置（Gene-Major Seek）+ 稀疏活跃行压缩 + K-PRL 增量去重 + 预计算 SQLite 查表 + 单进程融合托管（REST API + `/mcp` + 静态前端）**，将原本面向高配算力机（4 核以上、约 7 GB 常驻内存、21 GB 数据）的系统无损瘦身为可直接长期驻留 **2 vCPU / 2 GB RAM / 20 GB Disk** 轻型小服务器的生产架构。

---

## 0. 优化前后实测对比（全部来自 1 核实测）

| 资源 / 性能指标 | 优化前（全量默认版） | 优化后（Lite 单核轻量化版） | 缩减 / 实测表现 |
| :--- | :--- | :--- | :--- |
| **进程架构** | 6 进程（4 uvicorn + 1 MCP + 1 Next.js） | **1 进程**（单 uvicorn 同时托管 REST + `/mcp` + 静态页面 `/`） | 消除 Node.js 与多进程重复内存 |
| **CPU 占用** | 多核 BLAS + 4 workers | **严格 1 核**（`*_NUM_THREADS=1` + `taskset -c 0`，实测 `Cpus_allowed_list: 0`） | 完全满足“仅调用 1 核”，留出 1 核给系统 |
| **内存占用（VmRSS / 峰值 VmHWM）** | 4 workers 合计约 **6.7 GB**（单 worker ~1.7–2.0 GB） | 启动空载 **173 MB**；全接口+4并发+MCP 压测后峰值 **`VmHWM = 395 MB`**（常驻 **386 MB**） | **< 400 MB**（远低于 1 GB 红线） |
| **数据与前端磁盘占用** | `store/` 21 GB + `frontend/` 539 MB + Conda 1.4 GB | `store_lite/` **1.6 GB** + `frontend/out/` **2.2 MB** + `.venv-lite/`（精简依赖） | **总磁盘约 2.0–2.2 GB**（20 GB 盘绰绰有余） |
| **数值保真度（Lite vs Full）** | — | `LN_glom` & `DKD_tub` × 4 上下文：**Top-20 重合度 100%**；`renalconn` Spearman **0.999987–1.0000** | 几乎零精度损失 |
| **1 核查询延迟** | 259 ms（多核全量） | 全库签名检索 **345–791 ms**；通路/TF **194 ms**；化合物/靶点 **9–44 ms** | 1 核依然亚秒级响应 |

---

## 1. 在原高配算力机上生成轻量化制品（若已生成可跳过）

在原服务器 `/public/home/dongb/agent/renalkb` 中执行一次即可（不改动只读 `data/` 与全量 `store/`）：

```bash
cd /public/home/dongb/agent/renalkb
/public/home/dongb/miniforge3/envs/nephroperturb/bin/python scripts/09_build_lite_store.py
(cd frontend && PATH=/public/home/dongb/miniforge3/envs/nephroperturb/bin:$PATH NEXT_EXPORT=1 npm run build)
```

完成后将产出：
- `store_lite/`（约 **1.6 GB**：含基因主序矩阵、K-PRL 增量块、压缩位图指纹、`tdiki_explain` 与 `target_mimicry` 索引表、`.gmt.gz` 下载包）
- `frontend/out/`（约 **2.2 MB**：完整静态前端，目标机无需安装 Node.js）

---

## 2. 新小服务器部署步骤（2 核 / 2 GB RAM / 20 GB Disk）

### 第 1 步：拉取代码
```bash
git clone https://github.com/delect-aj/NephroPerturb.git ~/renalkb
cd ~/renalkb
```

### 第 2 步：仅传输预构建的 `store_lite/`（约 1.6 GB）
> 自 `v1.1.0` 起，预编译静态前端 `frontend/out/`（2.2 MB）已随 Git 仓库直接分发，`git clone` / `git pull` 会自动包含，因此**只需传输 `store_lite/`**。

在目标小服务器上执行（推荐先配置 `~/.ssh/config` 别名 `nephro-src` 指向 `dongb@c4a53664d2100454.natapp.cc:8089`）：
```bash
mkdir -p ~/renalkb/store_lite

rsync -avP nephro-src:/public/home/dongb/agent/renalkb/store_lite/ \
  ~/renalkb/store_lite/
```

### 第 3 步：一键轻量环境安装与启动（无需 Docker / Conda / Node.js）
```bash
cd ~/renalkb
bash deploy/bootstrap_lite.sh ~/renalkb
```
`bootstrap_lite.sh` 会自动完成：
1. 创建 `.venv-lite` 并仅安装最小依赖 `backend/requirements-lite.txt`（剔除 `scikit-learn` / `lightgbm` / `shap` / `scipy` / `numba` / `h5py` / `sqlalchemy` / `nodejs`）；
2. 校验 `store_lite/` 与 `frontend/out/` 完整性；
3. 调用 `deploy/run_lite.sh` 以**单进程、1 核线程限制（`taskset -c 0` + `*_NUM_THREADS=1`）、`--workers 1 --limit-concurrency 8`** 在 `:8091` 端口同时启动：
   - Web 页面：`http://<host>:8091/`
   - REST API：`http://<host>:8091/api/v1/...`
   - MCP Server（Streamable HTTP）：`http://<host>:8091/mcp`

### 第 4 步：配置 DeepSeek API Key（可选）
```bash
cd ~/renalkb
cp -n .env.example .env && chmod 600 .env
# 如需启用 DeepSeek 自然语言路由与总结，编辑 .env 填入 DEEPSEEK_API_KEY=<新Key>
# 不配置时系统自动工作在 0-LLM 纯确定性模式，功能 100% 正常
```

### 第 5 步：配置常驻守护与硬资源限制（推荐）
将用户级 `systemd` 服务写入 `~/.config/systemd/user/nephroperturb-lite.service`（模板已提供在 `deploy/nephroperturb-lite.service`，内置硬上限 **`CPUQuota=100%`、`AllowedCPUs=0`、`MemoryHigh=850M`、`MemoryMax=1024M`**）：
```bash
mkdir -p ~/.config/systemd/user
cp ~/renalkb/deploy/nephroperturb-lite.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now nephroperturb-lite
```

> **2 GB 小内存服务器稳妥建议**：建议系统至少开启 1–2 GB Swap 兜底（防止 `pip install` 或系统日常日志轮转期间触发突发 OOM），以及可选使用 `deploy/nginx-lite.conf.example` 作为单上游反代对外暴露 80/443 端口。

---

## 3. 更新已有小服务器部署（代码与前端迭代）

当只更新了后端路由/接口或静态前端页面（未改动 `requirements-lite.txt` 与 `store_lite/` 矩阵）时，**无需重新安装依赖、也无需重新 `rsync` 1.6 GB 的 `store_lite/`**，在小服务器执行：

```bash
cd ~/renalkb
rm -rf frontend/out            # 清理早期 rsync 的未跟踪目录（v1.1.0 起已由 Git 跟踪，否则 git pull 会冲突）
git pull origin main
systemctl --user restart nephroperturb-lite
sleep 3 && curl -fsS http://127.0.0.1:8091/health && echo
# 预期输出包含 "version":"1.1.0","mode":"lite","mcp_mounted":true
```

---

## 4. 验收与资源监控命令

```bash
# 1) 查看服务健康与 Lite 模式确认
curl -fsS http://127.0.0.1:8091/health
# 预期输出包含 "version":"1.1.0","mode":"lite","mcp_mounted":true

# 2) 验证 Web 静态界面与单端口 MCP
curl -fsS -o /dev/null -w "UI %{http_code}\n" http://127.0.0.1:8091/
NEPHRO_MCP_URL=http://127.0.0.1:8091/mcp python tests/test_mcp_e2e.py

# 3) 实测单进程实时内存、峰值内存与 1 核绑定
PID=$(pgrep -f "uvicorn app.main:app" | head -n 1)
grep -E "VmRSS|VmHWM|Threads|Cpus_allowed_list" /proc/$PID/status
```
