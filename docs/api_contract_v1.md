# API 与数据结构契约（v1）

**版本**：v1.0.0（定稿）；**v1.1.0 扩展**见 §9（第 10 周约定字段）  
**生效**：新功能（骨架、按页生成、进度、编辑）以本文件为准；长文档画像、章节、附件、检索策略、列表轻量项以 §9 为准。  
**Base URL**：本地开发 `http://127.0.0.1:8000`；前端 Vite 将 `/api` 代理到此后端。

**与 v0 关系**：[`api_contract_v0.md`](api_contract_v0.md) 中的创建任务、澄清、列表、导出、`Outline` 结构、`RetrievalHit` 等**继续有效**。v1 新增字段与接口；`POST /api/tasks/{task_id}/generate`（一次性全量生成）标记为**遗留**，新前端走 v1 流程。

本文件为全组**最小公约数**：字段名与枚举须一致；未文档化字段不得用于对外契约。

---

## 1. 全局约定

### 1.1 JSON

- `Content-Type: application/json; charset=utf-8`
- 时间：**ISO 8601**，示例 `2026-05-18T10:00:00+08:00`

### 1.2 任务状态 `TaskStatus`（对外五枚举，全小写）

| 值 | 含义 |
|----|------|
| `clarifying` | 收集需求澄清 |
| `pending` | 澄清已提交，可生成骨架或（遗留）全量生成 |
| `generating` | 处理中（含生成骨架、按页填充） |
| `done` | 成功；`outline` 应可用 |
| `failed` | 失败；`error` 建议非空 |

实现可有更细内部状态；**HTTP 响应里的 `status` 必须是上表五值之一**。细阶段写在 `progress.phase`（见 §4.1）。

### 1.3 工作流阶段 `WorkflowPhase`（`progress.phase`，全小写）

供进度展示与联调，**不替代** `TaskStatus`：

| 值 | 典型对应 `status` | 说明 |
|----|-------------------|------|
| `idle` | `pending` 等 | 无后台任务 |
| `skeleton_llm` | `generating` | 正在生成骨架 |
| `skeleton_ready` | `pending` | 骨架已就绪，等待用户修改或确认 |
| `retrieving_page` | `generating` | 正在为某一页检索 |
| `llm_page` | `generating` | 正在为某一页调用 LLM |
| `assembling` | `generating` | 合并各页为完整 `outline` |
| `saving` | `generating` | 持久化 |
| `regenerating_slide` | `generating` | 单页重生成中 |
| `done` | `done` | 流程结束（可与 `status=done` 同时出现） |
| `failed` | `failed` | 流程失败 |

实现可省略部分阶段，但**已出现的 `phase` 值不得改拼写**。

### 1.4 检索深度 `RetrievalDepth`

`L0` | `L1` | `L2`（含义同 v0）。

### 1.5 错误体

```json
{
  "error": {
    "code": "INVALID_STATE",
    "message": "可读说明",
    "details": {}
  }
}
```

常用 `error.code`：`VALIDATION_ERROR` (422)、`TASK_NOT_FOUND` (404)、`INVALID_STATE` (409)、`INTERNAL_ERROR` (500)、`GENERATION_TIMEOUT`、`RETRIEVAL_UNAVAILABLE`、`SLIDE_NOT_FOUND` (404，单页接口)。

### 1.6 契约版本字段

- 任务快照：`schema_version`，v1 实现建议 `"v1.0.0"`；含 §9 扩展时建议 `"v1.1.0"`
- 大纲：`outline.meta.schema_version`，建议 `"v1.0.0"` 或 `"v1.1.0"`

### 1.7 来源质量 `SourceQuality`（§9 `retrieval_policy`）

`low` | `medium` | `high`（全小写）。未传时由服务端默认，通常等价于 `medium`。

### 1.8 附件状态 `AttachmentStatus`（§9 `attachments`）

`pending` | `ready` | `failed`（全小写）。

### 1.9 长文档分析状态 `DocumentAnalysisStatus`（§9 `runtime`，可选）

`pending` | `running` | `done` | `failed`。表示 `document_profile` 是否已完成大模型预处理；规则字段可先由服务端同步写入。

---

## 2. 资源：`Task`（v1 快照）

### 2.1 `GET /api/tasks/{task_id}` 响应形状

在 v0 基础上增加 `progress`、`outline_skeleton`：

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "schema_version": "v1.0.0",
  "status": "pending",
  "created_at": "2026-05-18T10:00:00+08:00",
  "updated_at": "2026-05-18T10:05:00+08:00",
  "clarification": {
    "questions": [
      {
        "question_id": "goal",
        "prompt": "本次演示希望听众记住的一个核心结论是什么？",
        "answer": "string | null"
      }
    ],
    "submitted": true
  },
  "outline_skeleton": [
    {
      "slide_id": "s1",
      "title": "问题背景与目标",
      "intent": "说明为何要做这件事",
      "user_notes": null
    }
  ],
  "outline": null,
  "progress": {
    "phase": "skeleton_ready",
    "current": null,
    "total": 6,
    "message": "骨架已生成，请确认每页主题",
    "percent": null,
    "slide_id": null,
    "completed": null,
    "failed": null
  },
  "input": {
    "topic": "演示主题",
    "source_type": "long_document",
    "retrieval_depth": "L1",
    "document_title": "可选标题",
    "document_profile": {
      "summary": "全文摘要（规则或 LLM）",
      "key_points": ["要点一", "要点二"],
      "suggested_focus": "可选，建议 PPT 侧重",
      "segments": ["分段原文片段…"],
      "segment_count": 12,
      "char_count": 5200,
      "keywords": ["可选", "规则提取"]
    },
    "attachments": [
      {
        "document_id": "doc_abc",
        "filename": "参考材料.pdf",
        "status": "ready",
        "chunk_count": 42
      }
    ]
  },
  "runtime": {
    "document_analysis_status": "done",
    "retrieval_policy": {
      "retrieval_depth": "L1",
      "tavily_enabled": true,
      "prefer_user_doc": true,
      "source_quality": "medium",
      "force_refresh": false,
      "enable_fallback_deepen": true
    }
  },
  "error": null
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `clarification` | object \| null | 同 v0；**不得**含 `options`、题型等字段（§9.3） |
| `outline_skeleton` | `OutlineSkeleton` \| null | 未生成骨架前为 `null` |
| `outline` | `Outline` \| null | 按页生成完成后为完整大纲；见 §4.3、§9.2 |
| `progress` | `Progress` \| null | 无后台任务时可 `null`；生成中建议非空 |
| `input` | `TaskInput` \| null | v1.1：任务创建参数子集；**可不返回** `document_text`（过长） |
| `runtime` | `TaskRuntime` \| null | v1.1：编排与检索策略；见 §9.4 |
| `error` | object \| null | 同 v0；`failed` 时建议非空 |

- **`GET /api/tasks/{task_id}`**：建议返回上表全部顶层字段；`input` / `runtime` 在 v1.0 客户端可忽略。
- **`GET /api/tasks`**：列表项为 **轻量形状**（§9.6），**不要**要求与单条 `GET` 同形。
- **`GET /api/tasks/export`**：可与单条 `GET` 同形，或按评测需要截断大字段；字段名须一致。

### 2.2 创建任务、澄清（同 v0，v1.1 补充）

- **`POST /api/tasks`**：请求/响应见 v0 §2.1。实现创建后 `status` 多为 `clarifying`。  
  - `source_type=long_document` 时，服务端在 `input.document_profile` 写入规则字段（§9.1）；大模型 enrichment 完成后可更新同对象并置 `runtime.document_analysis_status=done`。
- **`PATCH /api/tasks/{task_id}/clarification`**：见 v0 §2.3。`submitted=true` → `status=pending`。  
  - 澄清题为**动态文本题**：`questions[]` 仅含 `question_id`、`prompt`、`answer`（§9.3）；由规则或模型生成，**无**选择题 `options`。

### 2.3 任务列表与导出、失败重试（同 v0）

- `GET /api/tasks`、`GET /api/tasks/export`、`POST /api/tasks/{task_id}/retry`：见 v0 §2.5–2.7。  
- `retry` 适用于**整任务**失败后的遗留/兼容路径；v1 按页失败优先用 §3.5 单页重试。

---

## 3. v1 新接口

### 3.1 生成骨架

**`POST /api/tasks/{task_id}/skeleton/generate`**

生成「短大纲」，仅页级结构，**不做 RAG**。

**前置**：`clarification.submitted === true`；`status` 为 `pending` 或 `clarifying`（实现若创建后即 clarifying，提交后 pending）。  
**冲突**：`generating` 且非骨架阶段、`done` 等 → `409 INVALID_STATE`。

请求体（可选）：

```json
{
  "idempotency_key": "optional-string"
}
```

响应 **`202 Accepted`**（异步，推荐）或 **`200 OK`**（同步，骨架很快时允许）：

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "generating",
  "accepted": true
}
```

完成后（轮询 `GET`）：`outline_skeleton` 非空；`progress.phase` 为 `skeleton_ready`；`status` 为 **`pending`**（等待用户改骨架或触发按页生成）。

错误：`409` 澄清未提交；`500` LLM/内部错误 → 可置 `failed`。

---

### 3.2 编辑骨架

**`PATCH /api/tasks/{task_id}/skeleton`**

**前置**：`outline_skeleton` 非空；`status` 为 `pending` 或 `progress.phase === skeleton_ready`；不得在按页生成进行中修改 → `409`。

请求体：

```json
{
  "slides": [
    {
      "slide_id": "s1",
      "title": "用户修改后的标题",
      "intent": "可选，本页意图一句话",
      "user_notes": "可选，给后续按页生成的额外要求"
    }
  ]
}
```

- `slides`：**完整列表**，表示替换整个骨架（增删改页均通过提交完整数组）。
- `slide_id`：客户端新建页时使用新 id（建议 `s{N}` 或 UUID 字符串），须在同一任务内唯一。

响应 **`200 OK`**：返回完整 `Task` 快照（§2.1）。

---

### 3.3 按页生成完整大纲

**`POST /api/tasks/{task_id}/slides/generate`**

按 `outline_skeleton` 逐页：检索（若策略需要）→ LLM 生成该页 bullets / speaker_notes → 合并为 `outline`。

**前置**：`outline_skeleton` 非空且至少 1 页；`clarification.submitted === true`；`status` 为 `pending` 或骨架已就绪；非 `generating`（除非幂等）→ 否则 `409`。

请求体（可选）：

```json
{
  "idempotency_key": "optional-string",
  "concurrency": 2,
  "retrieval_policy": {
    "retrieval_depth": "L1",
    "tavily_enabled": true,
    "prefer_user_doc": true,
    "source_quality": "medium",
    "force_refresh": false,
    "enable_fallback_deepen": true
  }
}
```

- `concurrency`：同时处理的页数上限，默认由服务端配置（建议 1–3）；超出范围忽略或 `422`。
- `retrieval_policy`：可选；见 §9.4。传入字段与 `task.runtime.retrieval_policy` **合并**后持久化；未传键沿用任务已有值或 `.env` / 服务端默认。
- **兼容**：仍允许在请求体顶层传 `retrieval_depth`、`tavily_enabled`、`force_refresh`（与 v1.0 实现一致）；与 `retrieval_policy` 同时出现时，以 **`retrieval_policy` 内同名键为准**。

响应 **`202 Accepted`**：

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "generating",
  "accepted": true,
  "idempotent": false
}
```

- 已在按页生成中重复提交且未失败：`idempotent: true`，不重复排队。

**进行中**：`progress` 示例：

```json
{
  "phase": "llm_page",
  "current": 3,
  "total": 6,
  "message": "正在生成第 3 页内容…",
  "percent": 50
}
```

**完成**：`status=done`，`outline` 非空，`progress.phase` 可为 `done` 或 `progress=null`。  
**失败**：`status=failed` 或保持 `generating` 自动重试（与 v0 策略一致时在 `error.details` 标明 `next_attempt`）。

客户端：**轮询 `GET /api/tasks/{task_id}`** 直至 `done` 或 `failed`。

---

### 3.4 编辑完整大纲

**`PATCH /api/tasks/{task_id}/outline`**

用户手动改正文，**不触发** LLM/RAG。

**前置**：`outline` 非空；`status === done`（实现若允许 `generating` 中禁止）→ `409`。

请求体（**部分更新**或**全量替换**二选一，实现须文档化；推荐支持全量）：

```json
{
  "title": "可选，整稿标题",
  "slides": [
    {
      "slide_id": "s1",
      "title": "页标题",
      "bullets": [
        { "bullet_id": "s1-b1", "text": "修改后的要点", "evidence_ids": ["ev_1"] }
      ],
      "speaker_notes": "讲者备注"
    }
  ],
  "evidence_catalog": []
}
```

- 若只改部分页，可只传 `slides` 中需改的项，但须约定实现是 merge 还是 replace；**v1 定稿约定：传 `slides` 即替换对应 `slide_id` 的页，未出现的页保持不变；传 `title` 则更新整稿标题**。
- `evidence_catalog` 可选；若传入则**整体替换**证据表。

响应 **`200 OK`**：完整 `Task` 快照。

---

### 3.5 单页重生成

**`POST /api/tasks/{task_id}/slides/{slide_id}/regenerate`**

仅重做一页：检索 + LLM，合并回现有 `outline`。

**前置**：`outline` 非空；`status` 为 `done` 或 `pending`（实现禁止 `generating` 中并发另一生成）→ `409`。  
未知 `slide_id` → `404 SLIDE_NOT_FOUND`。

请求体（可选）：

```json
{
  "user_instruction": "本页多加行业数据对比，语气更正式"
}
```

响应 **`202 Accepted`**：

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "generating",
  "accepted": true,
  "slide_id": "s3"
}
```

完成：该页 `slides[]` 更新，其它页不变；`status` 回到 `done`。  
进行中：`progress.phase=regenerating_slide`，`current`/`total` 可设为 `1/1`。

---

### 3.6 上传参考文档（v1.1，RAG 附件）

**`POST /api/tasks/{task_id}/documents/upload`**

**前置**：任务存在；`status` 非 `generating`（实现可放宽为仅禁止并发上传）→ 冲突时 `409`。

请求：`multipart/form-data`，字段名 `file`（单文件；格式与大小上限由服务端配置并在 413/415 时返回 `VALIDATION_ERROR`）。

响应 **`201 Created`** 或 **`200 OK`**（幂等重复上传同一文件名由实现决定）：

```json
{
  "document_id": "doc_abc",
  "filename": "参考材料.pdf",
  "status": "pending",
  "chunk_count": null
}
```

处理完成后，对应项出现在 `GET` 快照的 `input.attachments[]` 中，`status` 变为 `ready` 或 `failed`；`chunk_count` 在 `ready` 时建议非空。

---

## 4. 数据结构

### 4.1 `Progress`

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `phase` | `WorkflowPhase` | 是 | 当前阶段 |
| `current` | integer \| null | 否 | 当前页序号，从 **1** 开始 |
| `total` | integer \| null | 否 | 总页数 |
| `message` | string | 否 | 面向用户的短句 |
| `percent` | integer \| null | 否 | 0–100，估算值即可 |
| `slide_id` | string \| null | 否 | 按页生成/重生成时**当前页** id |
| `completed` | integer \| null | 否 | 已成功完成的页数（从 0 或 1 起算由实现固定，前后端须一致） |
| `failed` | integer \| null | 否 | 已失败页数（若支持单页失败继续） |

### 4.2 `OutlineSkeleton`

`outline_skeleton` 为 **数组**，顺序即页序：

```json
[
  {
    "slide_id": "s1",
    "title": "本页 PPT 标题",
    "intent": "本页要传达什么（一句话，可选）",
    "user_notes": "用户对该页的额外要求（可选）"
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `slide_id` | string | 页唯一 id |
| `title` | string | 非空 |
| `intent` | string \| null | LLM 生成骨架时的意图摘要 |
| `user_notes` | string \| null | 用户编辑，供按页生成时读取 |

### 4.3 `Outline`（完整大纲，同 v0 + v1.1）

在 v0 §3 基础上，每页 `slides[]` 项增加（均可选，按页生成稳定输出）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `key_message` | string \| null | 本页核心结论一句话 |
| `visual_suggestion` | string \| null | 配图/图表/版式建议 |
| `takeaway` | string \| null | 听众应带走的一句话或行动 |

章节（§9.2，二选一中的**推荐**写法）：

```json
{
  "title": "整份演示的主标题",
  "chapters": [
    {
      "chapter_id": "ch1",
      "title": "第一章 背景",
      "slide_ids": ["s1", "s2"]
    }
  ],
  "slides": [
    {
      "slide_id": "s1",
      "title": "本页标题",
      "chapter_id": "ch1",
      "key_message": "…",
      "bullets": [],
      "speaker_notes": null,
      "visual_suggestion": null,
      "takeaway": null
    }
  ],
  "evidence_catalog": [],
  "page_evidence_map": [
    {
      "slide_id": "s1",
      "evidence_ids": ["ev_1"],
      "coverage": 0.8
    }
  ],
  "meta": { "schema_version": "v1.1.0" }
}
```

- **`outline.chapters[]`（推荐）**：`chapter_id`、`title`、`slide_ids[]`（顺序即章内页序）。生成骨架或按页流程结束时写入。
- **`slide.chapter_id`（可选）**：与 `chapters` 冗余时须一致；仅实现章归属、不维护 `chapters` 数组时，可**仅**使用 `slide.chapter_id`，但全组须统一一种方案。
- **`page_evidence_map`**：按页汇总 `evidence_ids` 及可选 `coverage`（0–1）；由服务端根据 `slides[].bullets[].evidence_ids` 维护，客户端只读。

其余约定：

- 按页生成完成后，`outline.slides.length` 应与 `outline_skeleton.length` 一致（v1 **要求一致**）。
- `evidence_ids` 由服务端在检索后注入；LLM 不应作为证据来源（实现约束，非 HTTP 字段）。
- `meta` 可含 `retrieval_depth`、`generated_at`、`schema_version`；扩展键与 v0 相同规则。

### 4.4 `RetrievalHit`（内存/RAG，同 v0 §4）

不变。

---

## 5. 遗留接口（兼容）

### 5.1 一次性全量生成（deprecated）

**`POST /api/tasks/{task_id}/generate`**

行为见 v0 §2.4。新前端**不应**依赖；评测脚本可暂保留。  
与 v1 关系：不写入 `outline_skeleton`；成功后直接 `outline` + `done`。

---

## 6. v1 推荐端到端流程

```text
POST /api/tasks
  → PATCH .../clarification (submitted=true)     status: pending
  → POST .../skeleton/generate                 status: generating → pending, skeleton_ready
  → PATCH .../skeleton（可选，用户改标题）
  → POST .../slides/generate                   status: generating → done
  → PATCH .../outline（可选，用户改字）
  → POST .../slides/{slide_id}/regenerate（可选）
```

轮询：任意 `status=generating` 时读 `progress`；终止条件 `done` 或 `failed`。

---

## 7. 状态与操作矩阵（速查）

| 操作 | 允许的典型状态 |
|------|----------------|
| PATCH clarification | `clarifying`, `pending`（非 generating/done/failed） |
| POST skeleton/generate | `pending`（已提交澄清） |
| PATCH skeleton | `pending` + 已有 skeleton |
| POST slides/generate | `pending` + 已有 skeleton |
| PATCH outline | `done` |
| POST slide/regenerate | `done` |
| POST generate（遗留） | `pending`，已提交澄清 |
| POST retry | `failed` |

---

## 8. 协作提示

- Mock：`GET` 体须含 `progress`、`outline_skeleton` 字段（可为 `null`）；v1.1 Mock 建议含 `input.topic`、`input.document_profile`（长文档场景）。
- 评测：除 `outline` 完整性外，可增加 `outline_skeleton`、`progress.phase`、§9.6 列表轻量项校验。
- 状态机详图见 [`management/task_state_flow.md`](management/task_state_flow.md)。
- 第 10 周字段分工与验收见 [`management/week10计划.txt`](management/week10计划.txt) §七。

---

## 9. v1.1.0 扩展字段（第 10 周约定）

下列名称与 [`management/week10计划.txt`](management/week10计划.txt) §七一致；实现前须全组确认，**不得**擅自改名。

### 9.1 `DocumentProfile`（`task.input.document_profile`）

长文档（`source_type=long_document`）或分析完成后存在；短主题可为 `null`。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `summary` | string | 是 | 全文摘要；可先规则截断，再由 LLM 覆盖 |
| `key_points` | string[] | 是 | 3–12 条要点句 |
| `suggested_focus` | string \| null | 否 | 建议 PPT 叙事侧重（LLM） |
| `segments` | string[] | 否 | 规则分段原文片段，供检索/出题 |
| `segment_count` | integer | 否 | 分段数量 |
| `char_count` | integer | 否 | 正文字符数 |
| `keywords` | string[] | 否 | 规则关键词，可选保留 |

**合并规则**：LLM 预处理（B1）只覆盖/增强 `summary`、`key_points`、`suggested_focus`；**不得删除**已有 `segments`、`segment_count`、`char_count`、`keywords` 等规则字段。

### 9.2 `Chapter`（`outline.chapters[]`）

| 字段 | 类型 | 说明 |
|------|------|------|
| `chapter_id` | string | 章唯一 id，任务内唯一 |
| `title` | string | 章标题 |
| `slide_ids` | string[] | 属于本章的 `slide_id`，顺序即演示顺序 |

与 §4.3 `slide.chapter_id` 的关系见 §4.3。

### 9.3 `ClarificationQuestion`（不变 + 禁止项）

与 v0 相同，每项仅：

| 字段 | 类型 | 说明 |
|------|------|------|
| `question_id` | string | 稳定 id（规则或模型分配） |
| `prompt` | string | 展示给用户的题干 |
| `answer` | string \| null | 用户文本答案；未答为 `null` |

**禁止**在 `questions[]` 或 `clarification` 上出现：`options`、`type`、`choices`、`input_type` 等选择题/题型字段。模型澄清（B3）也仅输出上述三字段。

### 9.4 `RetrievalPolicy`（`task.runtime.retrieval_policy`）

由 `POST .../slides/generate` 请求体传入或创建时默认；持久化在 `runtime`，按页生成与单页重生成读取。

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `retrieval_depth` | `RetrievalDepth` | 任务 `input.retrieval_depth` 或 `L1` | 检索深度 |
| `tavily_enabled` | boolean | 环境配置 | 是否启用 Tavily |
| `prefer_user_doc` | boolean | `true`（长文档时） | 优先用户文档片段 |
| `source_quality` | `SourceQuality` | `medium` | 来源质量过滤阈值 |
| `force_refresh` | boolean | `false` | 忽略检索缓存 |
| `enable_fallback_deepen` | boolean | `true` | 证据不足时是否加深检索 |

未传的键：**不写入**或保留任务已有值；最终缺省由服务端 `.env` 补齐。实现可将合并结果同步到 `runtime.generation_*` 等内部键，但对外以 `retrieval_policy` 为准。

### 9.5 `Attachment`（`task.input.attachments[]`）

| 字段 | 类型 | 说明 |
|------|------|------|
| `document_id` | string | 附件唯一 id |
| `filename` | string | 原始文件名 |
| `status` | `AttachmentStatus` | `pending` \| `ready` \| `failed` |
| `chunk_count` | integer \| null | 分块数；`ready` 时建议非空 |

上传接口见 §3.6。

### 9.6 `TaskListItem`（`GET /api/tasks` 列表项）

列表**至少**包含：

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "input": { "topic": "演示主题" },
  "status": "done",
  "updated_at": "2026-06-02T10:00:00+08:00"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | string | 任务 id |
| `input.topic` | string | 创建时的主题（历史列表展示用） |
| `status` | `TaskStatus` | 五枚举 |
| `updated_at` | string (ISO 8601) | 最后更新时间 |

实现可附加 `created_at`、`source_type` 等，但**不得**用未文档化字段替代上表四元组。`export` 接口可返回更完整快照，见 §2.1。

### 9.7 `TaskInput` / `TaskRuntime`（`GET` 快照子对象）

**`TaskInput`**（`GET` 返回的子集，不含全文 `document_text` 除非产品明确要求）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `topic` | string | 同创建请求 |
| `source_type` | string | `short_topic` \| `long_document` |
| `retrieval_depth` | `RetrievalDepth` | 创建时选择 |
| `document_title` | string \| null | 可选 |
| `document_profile` | `DocumentProfile` \| null | §9.1 |
| `attachments` | `Attachment[]` | §9.5，默认 `[]` |

**`TaskRuntime`**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `document_analysis_status` | `DocumentAnalysisStatus` \| null | 长文档 LLM 预处理状态 |
| `retrieval_policy` | `RetrievalPolicy` \| null | §9.4 |

---

## 10. 变更记录

- **v1.1.0**（2026-06-02）：第 10 周约定。新增 `input.document_profile`、`input.attachments`、`runtime.retrieval_policy`、`runtime.document_analysis_status`；`outline.chapters` / `slide.chapter_id`、`page_evidence_map`、页级 `key_message` / `visual_suggestion` / `takeaway`；澄清题禁止 `options`；`GET /api/tasks` 列表轻量项；`POST .../documents/upload`；`Progress` 增量字段；`slides/generate` 请求 `retrieval_policy`。
- **v1.0.0**（2026-05-18）：定稿。新增 `progress`、`outline_skeleton`、`WorkflowPhase`；新增 skeleton / slides/generate / outline PATCH / slide regenerate；明确 v0 继承关系与遗留 `generate`。
