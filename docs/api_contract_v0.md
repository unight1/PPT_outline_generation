# API 与数据结构契约（v0）

**版本**：v0.1.0  
**生效**：以仓库内本文件为准；变更请 bump 版本号并在文末「变更记录」留一行说明。  
**Base URL**：本地开发为 `http://127.0.0.1:8000`。下文路径均相对于站点根（前端 Vite 将 `/api` 代理到此后端）。

本文件是全组**最小公约数**：前端 Mock、评测脚本、后端 stub 与真实实现，均应能映射到同一套字段名与枚举值。未列出的字段：实现方不得擅自用于对外契约（可内部使用）；若需扩展，走小版本升级（v0.1 → v0.2）并通知全组。

---

## 1. 全局约定

**1.1 JSON**

- 请求与响应体均为 `Content-Type: application/json; charset=utf-8`。
- 日期时间一律 **ISO 8601** 字符串，UTC 或带偏移均可，示例：`2026-04-15T12:00:00+08:00`。

**1.2 任务状态 `TaskStatus`（字符串枚举，全小写）**

- `pending`：已创建任务，尚未进入澄清或生成。
- `clarifying`：等待或正在收集需求澄清。
- `generating`：已触发大纲生成，处理中。
- `done`：生成成功，`outline` 可用。
- `failed`：失败；`error` 字段应非空。

实现侧状态机允许比上述更细，但**对外返回**必须落在以上五值之一（必要时在 `error.details` 里写细分子状态）。

**1.3 检索深度 `RetrievalDepth`（字符串枚举）**

与 RAG 档位对齐，供澄清表单或任务创建时选用：

- `L0`：轻量，少召回、低延迟。
- `L1`：默认平衡。
- `L2`：深度，多召回、可加重排（实现可后置）。

**1.4 错误体（Problem 形状）**

非 2xx 或业务失败（如 `failed`）时，HTTP 层与 JSON 建议统一为：

```json
{
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "可读说明",
    "details": {}
  }
}
```

- `code`：稳定机器可读标识，**大写下划线**。
- `message`：人类可读，可中文。
- `details`：可选，任意 JSON 对象（校验错误可把字段级原因放这里）。

**1.5 常用 `error.code`（v0 预留）**

- `VALIDATION_ERROR`：请求体不合法（建议 HTTP 422）。
- `TASK_NOT_FOUND`：未知 `task_id`（HTTP 404）。
- `INVALID_STATE`：当前状态不允许该操作（HTTP 409）。
- `INTERNAL_ERROR`：未分类服务端错误（HTTP 500）。

---

## 2. 资源：任务 `Task`

### 2.1 创建任务

**`POST /api/tasks`**

请求体：

```json
{
  "topic": "演示文稿主题，必填",
  "audience": "可选，听众/场景",
  "duration_minutes": 15,
  "language": "zh",
  "retrieval_depth": "L1",
  "raw_notes": "可选，用户粘贴的素材说明"
}
```

字段说明：

- `topic`：`string`，必填，非空。
- `audience`：`string | null`，可选。
- `duration_minutes`：`integer`，可选，默认 `15`，范围建议 5–120。
- `language`：`string`，可选，默认 `zh`。
- `retrieval_depth`：`RetrievalDepth`，可选，默认 `L1`。
- `raw_notes`：`string | null`，可选。

响应 **`201 Created`**：

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "created_at": "2026-04-15T10:00:00+08:00"
}
```

### 2.2 查询任务（含澄清与大纲快照）

**`GET /api/tasks/{task_id}`**

路径参数：`task_id`（UUID 字符串）。

响应 **`200 OK`**：

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "clarifying",
  "created_at": "2026-04-15T10:00:00+08:00",
  "updated_at": "2026-04-15T10:05:00+08:00",
  "clarification": {
    "questions": [
      {
        "question_id": "goal",
        "prompt": "本次演示希望听众记住的一个核心结论是什么？",
        "answer": "string | null"
      }
    ],
    "submitted": false
  },
  "outline": null,
  "error": null
}
```

字段说明：

- `status`：`TaskStatus`。
- `clarification`：`object | null`。无澄清流程时可为 `null`；有则为固定形状（见下）。
- `clarification.questions`：`array`，每项含 `question_id`、`prompt`、`answer`（未答为 `null`）。
- `clarification.submitted`：`boolean`，是否已提交澄清（提交后可由编排进入 `generating`）。
- `outline`：`Outline | null`，成功且 `status` 为 `done` 时应非 `null`。
- `error`：`object | null`，与 §1.4 的 `error` 内层形状相同；`status === "failed"` 时建议非 `null`。

### 2.3 提交或更新需求澄清

**`PATCH /api/tasks/{task_id}/clarification`**

请求体（部分更新允许，未出现的 `question_id` 视为不改）：

```json
{
  "answers": [
    { "question_id": "goal", "answer": "我们希望听众记住……" }
  ],
  "submitted": true
}
```

- `answers`：`array`，每项 `question_id` + `answer`（字符串，允许空串表示「跳过」由产品决定，v0 不强制）。
- `submitted`：`boolean`，可选。若为 `true`，表示用户确认提交，后端可将状态从 `clarifying` 迁出（具体迁到 `pending` 还是直接允许 `generate`，由编排决定，但**对外状态**仍须为五枚举之一）。

响应 **`200 OK`**：返回与 `GET /api/tasks/{task_id}` **相同形状**的完整 `Task` 对象。

错误示例：`409 INVALID_STATE`（例如在 `generating` 时修改澄清）。

### 2.4 触发大纲生成

**`POST /api/tasks/{task_id}/generate`**

请求体可为空对象：

```json
{}
```

响应 **`202 Accepted`**（推荐，表示已受理异步任务）：

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "generating",
  "accepted": true
}
```

客户端应随后轮询 `GET /api/tasks/{task_id}`，直到 `status` 为 `done` 或 `failed`。

错误示例：`409 INVALID_STATE`（澄清未提交就生成，若编排要求先澄清）。

---

## 3. 大纲结构 `Outline`

`Task.outline` 为该类型（`null` 表示尚未生成或失败被清空）。

```json
{
  "title": "整份演示的主标题",
  "slides": [
    {
      "slide_id": "s1",
      "title": "本页标题",
      "bullets": [
        {
          "bullet_id": "s1-b1",
          "text": "要点一句话",
          "evidence_ids": ["ev_1"]
        }
      ],
      "speaker_notes": "讲者备注，可选"
    }
  ],
  "evidence_catalog": [
    {
      "evidence_id": "ev_1",
      "snippet": "来自资料的一段原文摘录",
      "source_id": "doc_intro_md",
      "locator": "L12-L18 或 页3 段2",
      "score": 0.82,
      "confidence": 0.71
    }
  ],
  "meta": {
    "retrieval_depth": "L1",
    "generated_at": "2026-04-15T10:10:00+08:00"
  }
}
```

字段说明：

- `title`：`string`，整稿标题。
- `slides`：`array`，顺序即页序。
- `slide_id`：`string`，页级唯一标识。
- `title`（页内）：`string`，该页标题。
- `bullets`：`array`。
  - `bullet_id`：`string`，要点唯一标识。
  - `text`：`string`，要点正文。
  - `evidence_ids`：`string[]`，引用 `evidence_catalog[].evidence_id`；无引用可为 `[]`。
- `speaker_notes`：`string | null`，讲者备注。
- `evidence_catalog`：`array`，全稿统一的证据表。
  - `evidence_id`：`string`，全局唯一。
  - `snippet`：`string`，摘录。
  - `source_id`：`string`，资料标识（文件名、库内 id 等由 B 定义，对外保持字符串即可）。
  - `locator`：`string`，人类可读的页码/行号/段落位置描述。
  - `score`：`number | null`，检索相关分数，无则 `null`。
  - `confidence`：`number | null`，可选置信度 0–1。
- `meta`：`object`，至少可含 `retrieval_depth`、`generated_at`；其余键值对实现方可扩展，**前端与评测不应依赖未文档化键**。

---

## 4. RAG 模块对外的「单步检索」形状（供 B 对齐，HTTP 可选）

v0 **不要求**暴露为 REST；若 B 仅输出 Python 结构，建议**内存中**与下列 JSON 同形，便于以后 `POST /api/internal/retrieve` 一类接口直接沿用。

**`RetrievalHit`**

```json
{
  "snippet": "命中片段",
  "source_id": "资料标识",
  "locator": "位置描述",
  "score": 0.75,
  "confidence": 0.6
}
```

编排将 `Hit` 映射为 `Outline.evidence_catalog` 项时，负责分配 `evidence_id`（UUID 或 `ev_` 前缀均可，全稿唯一即可）。

---

## 5. 与前端、评测的协作提示（非规范性说明）

- C 的 Mock：`GET /api/tasks/{id}` 的 200 体可直接存为 `frontend/src/mocks/task.json` 等，字段名与本文件一致即可。
- D 的 golden：`outline` 整对象可作为期望子树做字段完整性检查；`TaskStatus` 与 `error.code` 做枚举校验。
- A 的 stub：可先固定返回示例 `task_id`，`generate` 后睡眠数秒再把 `status` 置为 `done` 并填入静态 `outline`。

---

## 6. 变更记录

- **v0.1.0**（2026-04-15）：首版，含任务 CRUD 流程、大纲与证据表、状态与错误约定。
