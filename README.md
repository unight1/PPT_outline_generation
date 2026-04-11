# PPT 大纲智能生成与内容补全系统

课程项目：Vue 3 + TypeScript 前端，Python（FastAPI）后端，MySQL / Redis（Docker）。

## 你需要先安装

- [Node.js](https://nodejs.org/)（LTS，含 npm）
- [Python 3.11+](https://www.python.org/downloads/)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)（用于 MySQL、Redis）

## 一次性准备

### 1. 环境变量

在仓库根目录复制示例文件并按需修改：

```bash
copy .env.example .env
```

（Linux / macOS：`cp .env.example .env`）

### 2. 启动数据库（MySQL + Redis）

在仓库根目录执行：

```bash
docker compose up -d
```

等待健康检查通过。默认端口：`3307`（MySQL）、`6379`（Redis）。

### 3. Python 后端

```bash
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

（Linux / macOS：`source .venv/bin/activate`）

浏览器打开 [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) 可看到 API 文档。

### 4. 前端

新开一个终端：

```bash
cd frontend
npm install
npm run dev
```

浏览器打开终端里提示的地址（一般为 [http://localhost:5173](http://localhost:5173)）。页面会请求 `/api/health`，由 Vite 代理到后端。

## 目录说明

| 路径 | 说明 |
|------|------|
| `backend/app/` | FastAPI 应用：`main.py`、配置、`api/routes/` |
| `frontend/src/` | Vue 入口与页面 |
| `docs/` | 项目说明与初步系统设计 |
| `docker-compose.yml` | 仅数据库与缓存（应用本地运行，便于调试） |

## 下一步开发建议

- 在 `backend/app/api/routes/` 增加任务、生成等接口
- 集成 LangGraph / LangChain 时把依赖写入 `backend/requirements.txt`
- 数据库表可用 SQLAlchemy 迁移（Alembic）逐步添加

## 常见问题

**前端显示「请求失败」**  
先确认后端已在 `8000` 端口运行，且前端用 `npm run dev`（不要只打开 `index.html` 文件）。

**`/api/health/ready` 里 mysql/redis 为 false**  
确认 Docker 已启动，且根目录 `.env` 中 `DATABASE_URL`、`REDIS_URL` 与 `docker-compose.yml` 一致。
