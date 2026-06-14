# Weeks 10–11 Biweekly Report — BE-1 (Backend Long Document + Chapters) + Bonus Features

## Completed Work

### BE-1a · B1 — Long Document LLM Preprocessing

Implemented LLM-based document enrichment that runs asynchronously after task creation:

- Created `backend/app/services/document_llm.py` (216 lines):
  - `enrich_document_profile()` — calls LLM 1–2 times to generate **summary**, **key_points** (3–12 items), and optional **suggested_focus** for the PPT narrative.
  - **Ultra-long documents** (>4000 chars): split into ~2000-char segments, summarize each with LLM, then merge segment summaries into a coherent full-text summary via a second LLM call.
  - `merge_enrichment_into_profile()` — merges LLM results with the rule-based profile (segments, char_count, keywords, segment_count), never deleting rule keys.
- Modified `backend/app/api/routes/tasks.py`:
  - `create_task` sets `runtime.document_analysis_status`:
    - `"running"` when `USE_REAL_LLM=true` and API key is configured — spawns `_enrich_document_profile_background()` in thread pool.
    - `"done"` immediately when `USE_REAL_LLM=false` (rule-based profile suffices).
  - On failure: status → `"failed"`, rule-based profile remains intact, task creation succeeds.
- Acceptance: `GET /api/tasks/{id}` shows LLM-generated summary/key_points in `input.document_profile`; `USE_REAL_LLM=false` never crashes; failed enrichment leaves rule profile in place.

### BE-1b · B2 — Per-Page Generation Uses Document

Enhanced the page generation pipeline to inject document context at every stage:

- Modified `backend/app/services/page_generation.py`:
  - `_build_page_query()` — now accepts optional `document_profile` parameter, injecting the document summary (≤400 chars) and top 5 key points into the retrieval query for each slide.
  - `_build_page_prompt()` — now includes a **"文档上下文"** (Document Context) block in the LLM prompt with document summary (≤600 chars) and key points (≤6 items), constraining generated content to stay consistent with the source document.
  - `_retrieve_for_pages_uncached()` — extracts `document_profile` from the task and passes it through to query construction.
  - `_generate_single_page()` — accepts `document_profile` parameter and forwards it to prompt builder.
  - `generate_pages_from_skeleton()` — extracts document profile from task input and passes it to `_generate_single_page`.
- Acceptance: long document tasks produce bullets/key_messages that are demonstrably related to the source text; works without BE-2 uploaded files (uses `document_text` directly).

### BE-1c · B4 — Chapter Structure (Backend Only)

Added chapter grouping throughout the skeleton and outline pipeline:

- Modified `backend/app/services/skeleton.py`:
  - `_skeleton_prompt` — LLM prompt now requests a `chapters[]` array (at least 2, max 5) alongside slides. Each chapter has `chapter_id`, `title`, and `slide_ids[]`.
  - `_normalize_skeleton` — parses LLM output for chapters, validates that `slide_ids` match actual slide IDs, assigns `chapter_id` to each slide.
  - `_build_stub_skeleton` — returns both slides and chapters (4 logical groups: Background/Market + Analysis/Challenges + Solution/Implementation + Summary/Future).
  - `_build_stub_chapters` — rule-based chapter assignment for fallback mode.
  - `generate_outline_skeleton` — return type changed from `list` to `dict{"slides": [...], "chapters": [...]}`.
- Modified `backend/app/services/page_generation.py`:
  - `merge_pages_to_outline` — accepts optional `chapters` parameter; includes `outline.chapters[]` in output; adds `chapter_id` field to each slide consistent with chapter grouping.
  - `generate_pages_from_skeleton` — reads `outline_skeleton_chapters` from task and passes through to merge.
- Modified `backend/app/api/routes/tasks.py`:
  - `complete_skeleton_generation` — extracts slides + chapters from new dict return, stores both.
  - `task_snapshot` — includes `outline_skeleton_chapters` in API response.
- Acceptance: API returns `outline.chapters[]` with ≥2 chapters and multiple pages per chapter; JSON matches contract §4.3 and §9.2.

### Tests Added

- `backend/tests/test_skeleton.py`: updated to assert chapters in skeleton output (stub chapters for fallback, LLM chapters for real mode).
- `backend/tests/test_page_generation.py`: added 7 new test cases:
  - `test_build_page_query_with_document_profile` — verifies document summary/key_points in query
  - `test_build_page_query_without_document_profile` — verifies no injection without profile
  - `test_build_page_prompt_includes_document_context` — verifies context block in prompt
  - `test_build_page_prompt_no_document_context` — verifies fallback "(无文档上下文)" text
  - `test_merge_pages_with_chapters` — verifies chapters appear in outline and chapter_id on slides
- All 144 existing tests continue to pass.

---

### Bonus: Login System (Week 11)

Added JWT-based authentication with preset users:

- **Backend**:
  - `backend/app/services/auth.py` — SHA256 PBKDF2 password hashing (zero extra dependencies), JWT token generation/verification with configurable secret and expiry.
  - `backend/app/api/routes/auth.py` — `POST /api/auth/login` endpoint returning `access_token`, `username`, and `role`.
  - Preset accounts: `admin` / `admin123` (admin role) and `user` / `user123` (user role).
- **Frontend**:
  - `frontend/src/components/LoginView.vue` — login form with username/password fields, error message display, token storage in `localStorage`.
  - `frontend/src/App.vue` — gates entire app behind login check; token auto-attached to all API requests via `Authorization: Bearer` header.
  - Logout button in top bar clears stored token and returns to login screen.

### Bonus: Evaluation Dataset Management (Week 11)

Added full CRUD for evaluation test cases:

- **Backend**:
  - `backend/app/api/routes/eval.py` — RESTful CRUD: `POST /api/eval`, `GET /api/eval`, `PATCH /api/eval/{id}`, `DELETE /api/eval/{id}`, `POST /api/eval/{id}/score`, `GET /api/eval/stats/summary`.
  - Data persists to `docs/evaluation/dataset_v0.json` (readable/editable by humans).
  - EvalCase model includes: topic, source_type, expected_depth, constraints, priority, status, task_id, score (1-5), evaluator, evidence_coverage, notes, timestamps.
- **Frontend**:
  - `frontend/src/components/EvalView.vue` — evaluation dashboard with stats cards (total/scored/avg score/high priority), case list with star ratings, modal for creating new cases.
  - Only visible to `admin` users — regular users see only the workflow.

### Bonus: PPTX Export (Week 11)

Added one-click PowerPoint export from generated outlines:

- **Backend**:
  - `backend/app/services/pptx_export.py` — generates `.pptx` files using `python-pptx` library:
    - Scheme: 13.33" × 7.5" (16:9) slides, blue (#2864D8) header bars with white titles.
    - Includes title slide, chapter divider slides (one per chapter), and content slides with key_message in italics and bullet points.
    - Outline slides not assigned to any chapter still rendered (handles partial chapter coverage).
  - `GET /api/tasks/{task_id}/export/pptx` — streams the `.pptx` file as a download.
- **Frontend**:
  - "下载 .pptx" button added to the result view bottom bar, alongside existing "下载 .md" button.

---

## Key Files Changed

| File | Changes |
|------|---------|
| `backend/app/services/document_llm.py` | **NEW** — LLM document enrichment (summary, key points, focus suggestion, segment merging) |
| `backend/app/services/skeleton.py` | Chapters in LLM prompt + normalization + stub chapter generation |
| `backend/app/services/page_generation.py` | Document context injection in query/prompt; chapters in merge output; chapter_id on slides |
| `backend/app/api/routes/tasks.py` | Document analysis background worker; chapters storage; PPTX export endpoint |
| `backend/app/services/auth.py` | **NEW** — JWT auth with PBKDF2 hashing, preset users |
| `backend/app/api/routes/auth.py` | **NEW** — Login endpoint |
| `backend/app/api/routes/eval.py` | **NEW** — Evaluation dataset CRUD + scoring + stats |
| `backend/app/services/pptx_export.py` | **NEW** — PPTX generation from outline data |
| `backend/tests/test_skeleton.py` | Updated for dict return format + chapters assertions |
| `backend/tests/test_page_generation.py` | 7 new tests for document context + chapters |
| `frontend/src/App.vue` | Login gate, eval view toggle, PPTX download, role-gated eval button |
| `frontend/src/components/LoginView.vue` | **NEW** — Login form |
| `frontend/src/components/EvalView.vue` | **NEW** — Evaluation dashboard |
| `frontend/src/api/httpApi.ts` | Auth header injection + login API |
| `frontend/src/api/evalApi.ts` | **NEW** — Evaluation API client |
| `frontend/src/types/task.ts` | EvalCase type definition |

---

## Verification

- **BE-1 self-test path**: POST long_document task → GET profile shows LLM summary/key_points → submit clarification → skeleton/generate produces chapters → slides/generate produces chapter-aware outline with document-relevant content.
- **Login**: `POST /api/auth/login` with `admin/admin123` returns JWT token; frontend gates app behind login, stores token, injects into subsequent requests.
- **Evaluation**: CRUD via Swagger UI; admin-only frontend page with stats and star ratings.
- **PPTX**: Download button on result page produces valid `.pptx` with title slide, chapter dividers, and content slides.
- **Tests**: 144/144 passing.

---

## Next Steps

- **API auth enforcement**: currently the `get_current_user` dependency exists but is not yet applied to task/eval routes — endpoints are publicly callable without a token.
- **Database migration**: table schema management via Alembic for production use.
- **E2E tests**: Playwright/Cypress tests covering login → create → clarify → skeleton → generate → export full path.
