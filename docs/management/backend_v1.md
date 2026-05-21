# 后端原型 v1 说明（成员 A）

面向前后端联调与评测脚本，描述运行方式、主流程与编排行为。字段与错误码以 [api_contract_v0.md](../api_contract_v0.md) 为准；状态机详见 [task_state_flow.md](./task_state_flow.md)。

## 1. 启动

```bash
cd backend
pip install -r requirements.txt
# 仓库根目录配置 .env：USE_REAL_LLM、OPENAI_API_KEY、TAVILY_API_KEY 等
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

| 变量 | 说明 |
|------|------|
| `USE_REAL_LLM=true` | 调用真实 LLM；`false` 时返回 stub 大纲 |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` | OpenAI 兼容网关 |
| `TAVILY_API_KEY` | L1/L2 网络检索；为空则仅本地向量检索 |
| `GENERATION_HARD_TIMEOUT_SECONDS` | 单次生成硬超时 |
| `GENERATION_MAX_RETRIES` | 失败后后台自动重试次数 |

## 2. 主流程 API

| 步骤 | 方法 | 路径 |
|------|------|------|
| 创建 | `POST` | `/api/tasks` |
| 查询 | `GET` | `/api/tasks/{task_id}` |
| 澄清 | `PATCH` | `/api/tasks/{task_id}/clarification` |
| 生成 | `POST` | `/api/tasks/{task_id}/generate` → `202`，后台异步 |
| 失败重试 | `POST` | `/api/tasks/{task_id}/retry`（仅 `failed`） |
| 评测导出 | `GET` | `/api/tasks/export` |

标准路径：`clarifying` →（澄清 `submitted=true`）→ `pending` → `generating` → `done` / `failed`。

## 3. 输入类型

- **短主题**：`source_type=short_topic`（默认），`topic` 必填。
- **长文档**：`source_type=long_document`，`document_text` 必填；服务端写入内部 `document_profile`：
  - `summary`：截断摘要
  - `segments`：分段正文（编排与页级检索使用）
  - `key_points` / `keywords`：规则提取，供生成 seed

## 4. 编排（`generate_outline_with_research`）

1. 推断目标页数（澄清中的页数答案 / 默认 8）。
2. **是否检索**（`L0`）：
   - `L1`/`L2`：始终检索；
   - 用户文案含「检索/引用/资料来源」等；
   - 长文档 `char_count >= 400`；
   - `raw_notes` 过短（&lt;80 字）或 L0 且澄清已提交。
3. 页级 research：按默认页目标逐页检索 → LLM 生成 → 剥离模型自填证据 → 注入检索证据 → **校验** `evidence_ids` 均在 `evidence_catalog`。
4. `outline.meta` 常见字段：`research_mode`、`retrieval_enabled`、`evidence_coverage_total`、`evidence_integrity_ok`。

## 5. 错误码（HTTP 层）

| code | HTTP | 场景 |
|------|------|------|
| `VALIDATION_ERROR` | 422 | 请求体验证失败、非法 UUID |
| `TASK_NOT_FOUND` | 404 | 未知 `task_id` |
| `INVALID_STATE` | 409 | 状态不允许当前操作 |
| `INTERNAL_ERROR` | 500 | 未分类服务端错误 |

生成阶段还可出现 `GENERATION_TIMEOUT`、`RETRIEVAL_UNAVAILABLE`（见任务 `error.code`）。

## 6. 评测最小 E2E（供 D）

```bash
BASE=http://127.0.0.1:8000
TASK=$(curl -s -X POST "$BASE/api/tasks" -H "Content-Type: application/json" \
  -d '{"topic":"评测样例","retrieval_depth":"L0"}' | jq -r .task_id)
curl -s -X PATCH "$BASE/api/tasks/$TASK/clarification" -H "Content-Type: application/json" \
  -d '{"answers":[{"question_id":"goal","answer":"结论"}],"submitted":true}'
curl -s -X POST "$BASE/api/tasks/$TASK/generate" -H "Content-Type: application/json" -d '{}'
# 轮询直至 status 为 done 或 failed
curl -s "$BASE/api/tasks/$TASK"
```

失败测试：主题包含 `[FAIL]` 可稳定得到 `failed` + `INTERNAL_ERROR`。
