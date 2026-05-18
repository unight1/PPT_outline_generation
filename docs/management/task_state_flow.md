# 任务状态流转说明（v1）

本文描述 v1 流程下的 `TaskStatus` 与 `progress.phase` 配合关系。HTTP 契约见 [`api_contract_v1.md`](../api_contract_v1.md)。

---

## 1. v1 主路径（推荐）

1. `POST /api/tasks` → 通常 `clarifying`
2. `PATCH .../clarification`，`submitted=true` → `pending`
3. `POST .../skeleton/generate` → `generating`（`progress.phase=skeleton_llm`）→ 完成 → `pending` + `outline_skeleton` 有值 + `progress.phase=skeleton_ready`
4. （可选）`PATCH .../skeleton` 用户改标题 → 仍 `pending`
5. `POST .../slides/generate` → `generating`（`retrieving_page` / `llm_page` / `assembling` 等）→ `done` + `outline` 非空
6. （可选）`PATCH .../outline` 用户改字 → `done`
7. （可选）`POST .../slides/{slide_id}/regenerate` → 短暂 `generating` → `done`

**轮询**：步骤 3、5、7 执行中客户端轮询 `GET /api/tasks/{id}`，读 `progress.message` 与 `progress.current/total`。

---

## 2. 遗留路径（v0 一次性生成）

- `POST .../generate`（澄清已提交）→ `generating` → `done` / `failed`
- 不使用 `outline_skeleton`；不经过按页流程
- 详见 v0 契约；新界面不应依赖

---

## 3. 异常与恢复

- `generating` / `done` / `failed` 下修改澄清 → `409 INVALID_STATE`
- 按页或全量生成失败：未超重试上限可保持 `generating` 并自动重试（`error.details.next_attempt`）；否则 `failed`
- `POST .../retry`：仅 `failed`，整任务重试（遗留兼容）
- 单页失败：优先 `POST .../slides/{slide_id}/regenerate`，不必整任务 retry
- 进程重启：恢复卡在 `generating` 的任务；陈旧任务可回写 `pending` 再排队（实现与 v0 相同，扩展支持 `slides/generate` 任务）

---

## 4. 对外状态 vs 细阶段

| 用户看到的 `status` | 常见 `progress.phase` |
|---------------------|------------------------|
| `clarifying` | `idle` 或 null |
| `pending` | `idle`, `skeleton_ready` |
| `generating` | `skeleton_llm`, `retrieving_page`, `llm_page`, `assembling`, `regenerating_slide` |
| `done` | `done` 或 null |
| `failed` | `failed` 或 null |

---

## 5. 联调建议

- 终止轮询：`status` 为 `done` 或 `failed`
- 进度展示：不要只依赖 `status=generating`，应读 `progress`
- 批量评测：`GET /api/tasks?status_filter=...`；v1 任务检查 `schema_version` 是否 `v1.0.0`
