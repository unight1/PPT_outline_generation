# 任务状态流转说明（A/C/D 对齐版）

本文用于前后端联调与评测对齐，描述 `TaskStatus` 的标准流转与异常分支。

## 1. 标准主路径

- `POST /api/tasks` 创建任务后，状态为 `clarifying`。
- 用户通过 `PATCH /api/tasks/{task_id}/clarification` 提交澄清：
  - `submitted=false`：保持 `clarifying`；
  - `submitted=true`：进入 `pending`。
- 仅当 `submitted=true` 时，`POST /api/tasks/{task_id}/generate` 才可触发，状态进入 `generating`。
- 生成成功后进入 `done`，并返回非空 `outline`。

## 2. 异常与恢复路径

- 在 `generating/done/failed` 状态下修改澄清，返回 `409 INVALID_STATE`。
- 生成执行异常时：
  - 若未超过重试上限：保持 `generating`，后台自动重试（`error` 中带 `next_attempt`）；
  - 若超过重试上限：进入 `failed`。
- 对 `failed` 任务可调用 `POST /api/tasks/{task_id}/retry` 显式重试。
- 进程重启时会恢复 `generating` 任务；陈旧任务可先回写为 `pending` 再重排队。

## 3. 关键错误码（生成阶段）

- `GENERATION_TIMEOUT`：生成超时（本地硬超时或上游超时）。
- `RETRIEVAL_UNAVAILABLE`：检索子系统不可用。
- `INTERNAL_ERROR`：未分类内部错误。

## 4. 联调与评测建议

- C 侧轮询终止条件：`done` 或 `failed`。
- D 侧批量评测可调用 `GET /api/tasks?status_filter=...` 拉取状态分布。
- 对 `pending` 状态任务可进行自动重试；`failed` 需要人工复核错误明细。
