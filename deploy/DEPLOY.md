# NephroPerturb 部署指南（GitHub → 新服务器）

## 0. 前置条件

- Linux（x86_64），**建议 ≥16 GB RAM、≥30 GB 磁盘**；无需 root（使用用户级 Miniforge）。
- 可访问 GitHub / PyPI / npm。
- 需要开放的端口：`8091`（REST）、`8092`（MCP）、`3000`（Web）。

> 数据说明：Git 仓库只含**代码与配置**。约 **12 GB** 的运行时数据（矩阵、注释、SQLite、模型、下载包）通过 rsync 从现服务器传输（见第 2 步）。原始上游数据 `annotations/raw/` 与 κ 扫描矩阵 `matrices/scan/` 不需要传输。

## 1. 推送代码到 GitHub（在当前服务器执行一次）

当前服务器 `/public/home/dongb/agent/renalkb` 已有 remote `git@github.com:delect-aj/NephroPerturb.git`（main 分支，tag `v1.0.0`）：

```bash
cd /public/home/dongb/agent/renalkb
git push -u origin main --tags
```

若服务器未配置 GitHub SSH key，可改用 HTTPS + Personal Access Token：

```bash
git remote set-url origin https://github.com/delect-aj/NephroPerturb.git
git push -u origin main --tags        # 按提示输入用户名 + PAT
```

**安全**：`.env` 已被 `.gitignore` 排除，API Key 不会进入仓库；推送前可 `git status` 确认无 `.env`。

## 2. 新服务器：拉取代码 + 迁移数据

```bash
# 2.1 代码
git clone https://github.com/delect-aj/NephroPerturb.git ~/renalkb
cd ~/renalkb

# 2.2 运行时数据（从现服务器 rsync，约 12 GB；使用你自己的 SSH 凭据/地址）
mkdir -p store
rsync -av --progress \
  --exclude 'matrices/scan' \
  --exclude '*_amean.npy' \
  --exclude 'annotations/raw' \
  --exclude '__pycache__' \
  -e "ssh -p 8089" \
  dongb@<当前服务器地址>:/public/home/dongb/agent/renalkb/store/ ~/renalkb/store/
```

传输后应包含：`matrices/*.npy|*.parquet|tau_null_tables_*.npz`、`chem/`、`annotations/*.parquet`、`downloads/*.gmt`、`models/`、`nephroperturb.db`。

## 3. 一键引导（安装环境 + 构建前端 + 启动服务）

```bash
cd ~/renalkb
bash deploy/bootstrap.sh ~/renalkb
```

脚本会：安装 Miniforge → 创建 `nephroperturb` 环境（Python 3.11 + Node 20）→ 安装 `backend/requirements.txt` → 校验数据 → `npm ci && npm run build` → 启动 API/MCP/Web 并做健康检查。

## 4. 配置 API Key

```bash
cd ~/renalkb
cp .env.example .env
chmod 600 .env
# 编辑 .env:  DEEPSEEK_API_KEY=<你的新 Key>
# 然后重启 API（读取 .env）：
pkill -f "uvicorn app.main" ; sleep 2
setsid nohup deploy/run_api.sh > logs/api.log 2>&1 < /dev/null &
```

> **务必轮换**：本次对话中出现过的 Key 应视为已泄露，请到 DeepSeek 控制台吊销并生成新 Key，只写入服务器 `.env`（权限 600）。
> 不配置 Key 时系统自动运行在 0-LLM 确定性模式，功能完整。

## 5. 可选：systemd 常驻 / Nginx 反代

```ini
# ~/.config/systemd/user/nephroperturb-api.service
[Unit]
Description=NephroPerturb API
[Service]
WorkingDirectory=%h/renalkb
Environment=ROOT=%h/renalkb
Environment=PY=%h/miniforge3/envs/nephroperturb/bin/python
ExecStart=%h/renalkb/deploy/run_api.sh
Restart=always
[Install]
WantedBy=default.target
```

`systemctl --user enable --now nephroperturb-api`（MCP/Web 同理）。Nginx 模板见 `deploy/nginx.conf.example`。

## 6. 验收检查

```bash
curl -s http://127.0.0.1:8091/health
curl -s http://127.0.0.1:8091/api/v1/cases | head -c 300
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3000/
curl -s -X POST http://127.0.0.1:8091/api/v1/query/signature \
  -H "Content-Type: application/json" \
  -d '{"up_genes":["COL1A1","FN1","TGFB1"],"down_genes":["NPHS1","PPARA"],"top_k":5}'
python tests/test_mcp_e2e.py        # 6 个 MCP 工具端到端
```

## 7. 更新流程（后续）

```bash
cd ~/renalkb && git pull
(cd frontend && npm ci && npm run build)
pkill -f "uvicorn app.main" || true
sleep 2
setsid nohup deploy/run_api.sh > logs/api.log 2>&1 < /dev/null &
```
（数据层更新仅在重建矩阵/模型时执行，需从源服务器重新 rsync `store/` 对应子目录。）
