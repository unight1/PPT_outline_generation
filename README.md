# PPT 大纲智能生成与内容补全系统

课程项目：基于 RAG + LLM 的 PPT 内容初稿生成。支持短主题与长文档输入，经澄清、骨架确认、按页检索生成，输出可编辑大纲与证据溯源。

**技术栈**：Vue 3 + TypeScript + Naive UI · FastAPI · MySQL · Redis · ChromaDB · Tavily

## 功能概览

| 模块 | 说明 |
|------|------|
| 主流程 | 创建 → 澄清 → 骨架 → 按页生成 → 结果编辑（四步导航） |
| RAG | L0/L1/L2 检索档位、页级定向检索、证据匹配与低可信标记 |
| 长文档 | LLM 摘要 enrichment、PDF/文本导入、按页注入文档上下文 |
| 扩展 | 任务历史/搜索/删除、PPTX 导出、登录门控、评测用例管理（admin） |

## 环境要求

- [Node.js](https://nodejs.org/) LTS
- [Python 3.10+](https://www.python.org/downloads/)（建议 3.10 或 3.11）
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)（MySQL + Redis）

## 快速启动

### 1. 配置环境变量

```bash
copy .env.example .env   # Linux/macOS: cp .env.example .env
```

按需填写 `OPENAI_API_KEY`、`OPENAI_BASE_URL`；启用真实 LLM 时设 `USE_REAL_LLM=true`。

### 2. 启动数据库

```bash
docker compose up -d
```

默认端口：MySQL `3307`，Redis `6379`。

### 3. 启动后端

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API 文档：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 [http://localhost:5173](http://localhost:5173)。

## 登录账号

| 用户 | 密码 | 权限 |
|------|------|------|
| `admin` | `admin123` | 主流程 + 评测管理 |
| `user` | `user123` | 仅主流程 |

## 目录结构

```
backend/app/          # FastAPI：routes / services / retrieval
frontend/src/         # Vue 单页应用（App.vue + components/）
docs/                 # API 契约、状态流转、评测与项目管理文档
docker-compose.yml    # MySQL + Redis
```

## 文档

- API 契约（v1）：`docs/api_contract_v1.md`
- 任务状态流转：`docs/management/task_state_flow.md`
- 评测指标说明：`docs/evaluation/`

## 常见问题

**登录或接口报「请求失败」**  
确认后端在 `8000` 端口运行，且使用 **venv 内的 Python** 启动 uvicorn（勿混用全局 Python）。

**按页生成在 retrieving_page 阶段失败**  
多为 `transformers` 版本不兼容，在 venv 中执行 `pip install -r requirements.txt` 后重启后端。

**`/api/health/ready` 中 mysql/redis 为 false**  
检查 Docker 是否启动，`.env` 中 `DATABASE_URL`、`REDIS_URL` 是否与 `docker-compose.yml` 一致。

**首次按页生成较慢**  
启动时会预热 embedding 模型；也可在 `.env` 设 `RETRIEVAL_WARMUP_ON_STARTUP=false` 推迟到首次请求。
