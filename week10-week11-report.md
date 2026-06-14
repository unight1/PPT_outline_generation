# Weeks 10–11 Biweekly Report — BE-1（后端 1）

## 已完成工作

### BE-1a · 长文档 LLM 预处理
- 新建 `document_llm.py`：异步调用 LLM 生成 `summary`、`key_points`、`suggested_focus`
- 超长文档分段摘要后合并；失败降级规则 profile，任务不中断
- `runtime.document_analysis_status` 状态追踪（pending → running → done / failed）

### BE-1b · 按页生成注入文档上下文
- `_build_page_query` / `_build_page_prompt` 注入文档摘要与关键要点
- 每页检索 query 和 LLM 输入包含文档上下文，不塞全文

### BE-1c · 章节结构
- 骨架生成输出 `chapters[]`（chapter_id / title / slide_ids），每页带 `chapter_id`
- `merge_pages_to_outline` 保留章节，`GET /api/tasks` 返回章节结构
- 测试新增 7 个用例，全部 144 测试通过

### 登录系统
- JWT 鉴权：`POST /api/auth/login`，PBKDF2 密码哈希，预设 admin / user
- 前端 LoginView 登录页，token 存 localStorage，API 自动携带 Bearer header
- admin 专属评测入口，user 仅见工作台

### 评测数据集管理
- `CRUD /api/eval` + 评分 + 统计摘要，数据持久化到 `dataset_v0.json`
- 前端 EvalView：统计卡片 + 用例列表 + 星级评分 + 新建弹窗

### PPTX 导出
- `GET /api/tasks/{id}/export/pptx`：蓝色标题栏 + 要点列表 + 章节分隔页
- 前端结果页 "下载 .pptx" 按钮，修复中文文件名编码

### 任务管理增强
- `DELETE /api/tasks/{id}`：删除接口 + 侧栏悬停 ✕ 按钮
- `GET /api/tasks?search=`：主题关键词搜索 + 前端搜索框
- `GET /api/tasks/stats/tokens`：Token 用量统计，按页汇总 prompt/completion tokens

### PDF 文档导入
- `POST /api/utils/parse-pdf`：后端解析 PDF 提取文本
- `POST /api/utils/analyze-document`：LLM 分析文档，自动建议 PPT 主题/听众/补充材料
- 前端上传 PDF 后主题、听众、备注自动填充

### 前端打磨
- 空状态：无任务时显示引导图标 + 文案
- 骨架屏：任务列表加载时 shimmer 占位动画
- 配图建议/行动建议提示词优化，强制 LLM 必填
- 按钮嵌套 + CSS 多余括号修复

## 关键文件

| 文件 | 操作 |
|------|------|
| `backend/app/services/document_llm.py` | 新建 |
| `backend/app/services/auth.py` | 新建 |
| `backend/app/services/pptx_export.py` | 新建 |
| `backend/app/api/routes/auth.py` | 新建 |
| `backend/app/api/routes/eval.py` | 新建 |
| `backend/app/api/routes/utils.py` | 新建 |
| `backend/app/services/skeleton.py` | 修改（章节） |
| `backend/app/services/page_generation.py` | 修改（文档上下文 + prompt 优化 + token 统计） |
| `backend/app/api/routes/tasks.py` | 修改（删除/搜索/统计/导出/章节） |
| `frontend/src/components/LoginView.vue` | 新建 |
| `frontend/src/components/EvalView.vue` | 新建 |
| `frontend/src/api/evalApi.ts` | 新建 |
| `frontend/src/App.vue` | 修改（登录门控/评测切换/PDF上传/自动填充/搜索/删除） |
| `frontend/src/components/TaskSidebar.vue` | 修改（搜索/删除/空状态/骨架屏） |
| `backend/tests/test_skeleton.py` | 修改 |
| `backend/tests/test_page_generation.py` | 新增 7 用例 |

## 测试

全部 144 单元测试通过。快速验收路径：
1. 登录 `admin/admin123` → 创建长文档 → 上传 PDF → 主题/听众自动填充
2. 澄清提交 → 骨架生成（含章节） → 按页生成（配图建议+行动建议有内容）
3. 结果页下载 PPTX → 搜索/删除任务 → 查看评测页 → Token 统计
