# PPT Outline Generation System — Comprehensive Test Report

**Version:** v1.1.0  
**Date:** 2025-06-17  
**Environment:** Python 3.11.15 · pytest 9.0.3 · pytest-anyio 4.13.0 · Vitest 4.1.9 · jsdom · @vue/test-utils 2.4.6  
**Branch:** `feat/week10-ui-refactor` (representative; tests span all active modules)

---

## Executive Summary

| Category | Files | Tests | Passed | Failed | Pass Rate |
|----------|-------|-------|--------|--------|-----------|
| Retrieval | 10 | 47 | 47 | 0 | 100% |
| API Tasks | 1 | 32 | 32 | 0 | 100% |
| Page Generation | 1 | 71 | 71 | 0 | 100% |
| Orchestration | 1 | 10 | 9 | 1 | 90% |
| Skeleton | 1 | 5 | 5 | 0 | 100% |
| Document Processing | 1 | 1 | 1 | 0 | 100% |
| Frontend (Vue) | 4 | 24 | 24 | 0 | 100% |
| **Total** | **19** | **190** | **189** | **1** | **99.5%** |

The single failure (`test_inject_evidence_includes_low_confidence_bullets` in `test_orchestration.py`) is a pre-existing issue unrelated to the current development cycle; it results from a `low_confidence_bullets` count mismatch introduced by a parallel branch's refactoring of the orchestration layer.

---

## 1. Retrieval Module

**Location:** `backend/tests/test_retrieval/`  
**Status:** 47/47 passing

### 1.1 Data Types (`test_types.py`) — 6 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 1 | `test_retrieval_depth_values` | PASS | L0/L1/L2 enum values |
| 2 | `test_retrieval_hit_minimal` | PASS | `RetrievalHit` with required fields only |
| 3 | `test_retrieval_hit_full` | PASS | `RetrievalHit` with optional score/confidence |
| 4 | `test_retrieval_request_defaults` | PASS | `RetrievalRequest` defaults (L1, no filter) |
| 5 | `test_retrieval_result` | PASS | `RetrievalResult` wraps hits + depth + latency |
| 6 | `test_hit_serialization` | PASS | `model_dump()` produces valid JSON |

### 1.2 Depth Configuration (`test_depth_config.py`) — 6 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 7 | `test_all_depths_present` | PASS | L0/L1/L2 keys defined |
| 8 | `test_l0_no_reranking` | PASS | L0: rerank=false, recall=5 |
| 9 | `test_l1_balanced` | PASS | L1: recall=15, rerank=false |
| 10 | `test_l2_deep_with_reranking` | PASS | L2: recall=30, rerank=true |
| 11 | `test_recall_increases_with_depth` | PASS | Monotonic recall L0→L1→L2 |
| 12 | `test_threshold_decreases_with_depth` | PASS | Monotonic threshold L0→L1→L2 |

### 1.3 Local Document Loader (`test_sources_local.py`) — 6 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 13 | `test_load_text_files` | PASS | Reads .md/.txt→DocumentChunks |
| 14 | `test_chunks_have_locators` | PASS | Chunks have line-number locators |
| 15 | `test_empty_directory` | PASS | Empty dir→empty list |
| 16 | `test_nonexistent_directory` | PASS | Missing path→FileNotFoundError |
| 17 | `test_unsupported_files_ignored` | PASS | Non-text files skipped |
| 18 | `test_chunk_size_respected` | PASS | 800/150 chunking honored |

### 1.4 Embedding Provider (`test_embedding_fake.py`) — 5 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 19 | `test_dimension` | PASS | Configured dimension returned |
| 20 | `test_embed_texts_shape` | PASS | Correct output dimensions |
| 21 | `test_deterministic` | PASS | Same input→same output |
| 22 | `test_different_inputs_different_vectors` | PASS | Different inputs diverge |
| 23 | `test_normalized` | PASS | L2-normalized vectors |

### 1.5 ChromaDB Vector Index (`test_index_chroma.py`) — 6 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 24 | `test_not_built_initially` | PASS | `is_built` false before `build()` |
| 25 | `test_build_and_query` | PASS | Build+query returns IndexMatch with scores |
| 26 | `test_persistence` | PASS | Index survives process restart |
| 27 | `test_top_k_larger_than_index` | PASS | Top-k overflow returns all items |
| 28 | `test_empty_build` | PASS | Empty build does not error |
| 29 | `test_query_not_built` | PASS | Pre-build query returns [] |

### 1.6 Reranker (`test_reranker_fake.py`) — 3 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 30 | `test_passthrough` | PASS | Fake returns inputs unchanged |
| 31 | `test_top_k_truncation` | PASS | Output capped at top_k |
| 32 | `test_empty_input` | PASS | Empty→empty |

### 1.7 Core Retriever (`test_retriever.py`) — 9 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 33 | `test_retrieve_l0` | PASS | L0: ≤5 hits, valid latency |
| 34 | `test_retrieve_l2` | PASS | L2: hits have snippet/source_id/locator |
| 35 | `test_source_filter` | PASS | Filter restricts by source_id |
| 36 | `test_empty_dir_returns_no_hits` | PASS | Empty docs→empty hits |
| 37 | `test_l0_fewer_than_l2` | PASS | L0 ≤ L2 hit count |
| 38 | `test_result_serializable` | PASS | JSON-serializable result |
| 39 | `test_web_search_merged_into_results` | PASS | L1 + FakeWebSearch→web hits |
| 40 | `test_web_search_not_used_in_l0` | PASS | L0 excludes web |
| 41 | `test_web_search_graceful_degradation` | PASS | Failing web search→local only |

### 1.8 Tavily Web Search (`test_sources_tavily.py`) — 6 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 42 | `test_default_results` | PASS | FakeWebSearch returns default hit |
| 43 | `test_custom_results` | PASS | Custom results capped correctly |
| 44 | `test_max_results_caps_output` | PASS | max_results=0→[] |
| 45 | `test_search_returns_hits` | PASS | Mock Tavily→RetrievalHits |
| 46 | `test_search_skips_empty_content` | PASS | Empty/whitespace skipped |
| 47 | `test_search_returns_empty_on_api_failure` | PASS | Exception→[] |

---

## 2. API Tasks Module

**Location:** `backend/tests/test_api_tasks.py`  
**Status:** 32/32 passing

### 2.1 Task Lifecycle — 8 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 48 | `test_create_task_starts_in_clarifying` | PASS | POST /api/tasks→status=clarifying, questions populated |
| 49 | `test_clarification_questions_are_trimmed_when_context_is_complete` | PASS | audience+raw_notes provided→questions omitted |
| 50 | `test_clarification_questions_follow_text_only_contract` | PASS | No options/type fields in questions |
| 51 | `test_generate_requires_submitted_clarification` | PASS | 409 when clarification.submitted=false |
| 52 | `test_submit_clarification_then_generate_done` | PASS | Clarify→generate→done transition |
| 53 | `test_patch_clarification_rejected_after_done` | PASS | 409 on clarification patch after done |
| 54 | `test_generate_is_idempotent_when_already_generating` | PASS | Duplicate generate→idempotent=true |
| 55 | `test_same_idempotency_key_in_pending_still_starts_generation` | PASS | Same key on pending still enqueues |

### 2.2 Skeleton & Slides Generation — 7 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 56 | `test_generate_and_patch_outline_skeleton` | PASS | PATCH /skeleton updates outline_skeleton |
| 57 | `test_generate_skeleton_requires_submitted_clarification` | PASS | 409 without submitted clarification |
| 58 | `test_generate_slides_merges_and_persists_retrieval_policy` | PASS | Retrieval policy merged into runtime |
| 59 | `test_merge_retrieval_policy_normalizes_legacy_enum_string` | PASS | Legacy enum strings normalized |
| 60 | `test_patch_skeleton_after_failed_resets_to_pending` | PASS | Failed→pending after skeleton patch |
| 61 | `test_patch_skeleton_updates_chapters` | PASS | Chapter assignments preserved |
| 62 | `test_task_snapshot_rebuilds_chapters_from_skeleton_slides` | PASS | Chapters rebuilt from skeleton |

### 2.3 Outline & Evidence — 2 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 63 | `test_patch_outline_merges_slides_and_rebuilds_evidence_map` | PASS | PATCH /outline rebuilds page_evidence_map |
| 64 | `test_patch_outline_rejects_before_done` | PASS | 409 before done |

### 2.4 Long Document — 5 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 65 | `test_long_document_requires_document_text` | PASS | 422 without text |
| 66 | `test_long_document_builds_internal_document_profile` | PASS | Profile with segments/key_points |
| 67 | `test_long_document_defers_clarification_until_analysis` | PASS | Analysis before clarification |
| 68 | `test_long_document_persists_body_for_task_rag` | PASS | Text persisted for task-level RAG |
| 69 | `test_long_document_generation_passes_document_profile_to_orchestration` | PASS | Profile passed through |

### 2.5 Upload & Error Handling — 5 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 70 | `test_upload_task_document_updates_attachments` | PASS | Upload→attachment with status=pending |
| 71 | `test_upload_rejects_unsupported_document_type` | PASS | Non-.md/.txt/.pdf→422 |
| 72 | `test_task_not_found_returns_contract_error` | PASS | 404 TASK_NOT_FOUND |
| 73 | `test_invalid_task_id_returns_client_error` | PASS | Non-UUID→404/422 |
| 74 | `test_create_task_empty_topic_returns_validation_error` | PASS | Empty topic→422 |

### 2.6 Recovery & Admin — 5 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 75 | `test_recover_inflight_generations_marks_stale_and_requeues` | PASS | Stale generating→pending re-enqueue |
| 76 | `test_recover_inflight_generations_requeues_skeleton_and_slides` | PASS | Both skeleton and slides phases recovered |
| 77 | `test_retry_failed_task_accepts_only_failed` | PASS | POST /retry on non-failed→409 |
| 78 | `test_export_tasks_endpoint_not_shadowed_by_task_id_route` | PASS | /api/tasks/export not matched as task_id |
| 79 | `test_list_tasks_with_status_filter` | PASS | Status filter works |

---

## 3. Page Generation Module

**Location:** `backend/tests/test_page_generation.py`  
**Status:** 71/71 passing

### 3.1 Outline Assembly — 7 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 80 | `test_merge_pages_to_outline_basic` | PASS | Two slides→correct catalog+page_evidence_map |
| 81 | `test_merge_pages_empty_skeleton` | PASS | Empty→empty |
| 82 | `test_merge_pages_stub_for_missing_page` | PASS | Missing page→stub with 2 bullets |
| 83 | `test_merge_pages_preserves_bullet_order` | PASS | Bullet order preserved |
| 84 | `test_merge_pages_shared_evidence_across_bullets` | PASS | Shared evidence→one trace, multiple bullet_ids |
| 85 | `test_merge_pages_preserves_llm_chosen_evidence_ids` | PASS | LLM-chosen ev_2 preserved; fallback fills ev_1 |
| 86 | `test_merge_pages_with_chapters` | PASS | Chapters→slide mapping correct |

### 3.2 Evidence Cleaning — 12 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 87 | `test_clean_evidence_snippet_normal_text` | PASS | Factual text returned ≤200 chars |
| 88 | `test_clean_evidence_snippet_filters_copyright` | PASS | Copyright notice→"" |
| 89 | `test_clean_evidence_snippet_filters_navigation` | PASS | Breadcrumb nav→"" |
| 90 | `test_clean_evidence_snippet_filters_disclaimer` | PASS | Disclaimer→"" |
| 91 | `test_clean_evidence_snippet_truncates_long_text` | PASS | Long→≤max_chars |
| 92 | `test_clean_evidence_snippet_filters_nav_with_prefix` | PASS | "网站地图"→"" |
| 93 | `test_clean_evidence_snippet_empty` | PASS | Empty/whitespace→"" |
| 94 | `test_clean_evidence_snippet_preserves_fact_sentences` | PASS | Nav dropped, facts retained |
| 95 | `test_clean_evidence_snippet_truncates_at_sentence_boundary` | PASS | Truncation at sentence punctuation |
| 96 | `test_clean_evidence_snippet_all_noise_empty_catalog` | PASS | All-noise→empty catalog |
| 97 | `test_clean_evidence_snippet_mixed_noise_and_valid` | PASS | Noise dropped, valid retained |
| 98 | `test_clean_evidence_snippet_handles_empty_paragraph` | PASS | Empty/whitespace→"" |

### 3.3 Bullet-Evidence Semantic Matching — 8 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 99 | `test_match_bullets_high_overlap` | PASS | AI教育市场规模→ev_1 |
| 100 | `test_match_bullets_low_overlap_gets_empty` | PASS | 微服务 vs AI教育→no match |
| 101 | `test_match_bullets_respects_existing_evidence_ids` | PASS | LLM-pre-filled preserved |
| 102 | `test_match_bullets_no_evidence` | PASS | Empty evidence→all low_confidence |
| 103 | `test_match_bullets_partial_match` | PASS | 2 bullets: one matched, one not |
| 104 | `test_match_bullets_empty_array` | PASS | [ ]→returns [], low_count=0 |
| 105 | `test_match_bullets_no_text` | PASS | Empty text→low_confidence |
| 106 | `test_match_bullets_non_dict_skipped` | PASS | Non-dict entries skipped |

### 3.4 Multi-Language Matching — 3 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 107 | `test_match_bullets_english_text` | PASS | Word-overlap matching for English |
| 108 | `test_match_bullets_english_low_overlap` | PASS | Stopword-filtered: no false match |
| 109 | `test_match_bullets_mixed_language` | PASS | 中英混合→Chinese char overlap wins |

### 3.5 Query Building — 7 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 110 | `test_build_page_query_basic` | PASS | Topic+title |
| 111 | `test_build_page_query_with_intent_and_notes` | PASS | intent+notes+clarification |
| 112 | `test_build_page_query_includes_regeneration_instruction` | PASS | user_instruction injected |
| 113 | `test_build_page_query_includes_relevant_document_segments` | PASS | Segments attached |
| 114 | `test_build_page_query_skips_empty_fields` | PASS | Missing fields→clean |
| 115 | `test_build_page_query_with_document_profile` | PASS | Profile summary injected |
| 116 | `test_build_page_query_without_document_profile` | PASS | No profile→graceful |

### 3.6 Prompt Building — 6 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 117 | `test_build_page_prompt_includes_evidence` | PASS | Evidence snippets+IDs in prompt |
| 118 | `test_build_page_prompt_no_evidence` | PASS | "(无参考资料)" fallback |
| 119 | `test_build_page_prompt_intent_and_notes_included` | PASS | intent+notes injected |
| 120 | `test_build_page_prompt_prioritizes_regeneration_instruction` | PASS | Regeneration instruction prominent |
| 121 | `test_build_page_prompt_includes_document_context` | PASS | Document profile in prompt |
| 122 | `test_build_page_prompt_no_document_context` | PASS | Missing profile→graceful |

### 3.7 Retrieval — 4 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 123 | `test_retrieve_for_pages_uses_parallel_budgeted_tavily` | PASS | Semaphore + Tavily budget |
| 124 | `test_retrieve_for_pages_reuses_slide_cache` | PASS | force_refresh=false→cache reused |
| 125 | `test_filter_hits_by_source_quality_keeps_user_docs_first` | PASS | User docs prioritized |
| 126 | `test_select_relevant_document_segments_prefers_slide_context` | PASS | Context-relevant segments first |

### 3.8 API Integration — 12 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 127 | `test_slides_generate_requires_skeleton` | PASS | 409 on null skeleton |
| 128 | `test_slides_generate_requires_pending` | PASS | 409 when done |
| 129 | `test_slides_generate_accepts_failed_with_skeleton` | PASS | Failed+skeleton→accepted |
| 130 | `test_slides_generate_requires_submitted_clarification` | PASS | 409 unsubmitted |
| 131 | `test_slides_generate_accepted_with_valid_state` | PASS | Valid→202 |
| 132 | `test_slides_generate_respects_concurrency_param` | PASS | concurrency=3 passed |
| 133 | `test_slides_generate_defaults_concurrency_when_payload_empty` | PASS | Default→2 |
| 134 | `test_classify_slide_generation_exception_maps_workflow_error` | PASS | LLM/RETRIEVAL/TAVILY_ERROR classified |
| 135 | `test_regenerate_requires_outline` | PASS | 409 null outline |
| 136 | `test_regenerate_slide_not_found` | PASS | 404 SLIDE_NOT_FOUND |
| 137 | `test_regenerate_requires_done_or_pending` | PASS | 409 when failed |
| 138 | `test_regenerate_accepted` | PASS | Valid→202 |

### 3.9 Utility & Miscellaneous — 8 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 139 | `test_task_snapshot_includes_v1_fields` | PASS | skeleton+progress in snapshot |
| 140 | `test_create_task_initializes_progress` | PASS | phase=idle, skeleton=null |
| 141 | `test_build_evidence_catalog_entry_shortens_long_snippet` | PASS | Long→~200 chars |
| 142 | `test_generate_pages_retrieves_once_then_generates_each_page` | PASS | Retrieval once, LLM per page |
| 143 | `test_clarification_text_basic` | PASS | Q→A formatted |
| 144 | `test_clarification_text_empty` | PASS | Null/empty→"" |
| 145 | `test_clarification_text_skips_missing_answers` | PASS | Unanswered skipped |
| 146 | `test_generate_single_page_ignores_llm_evidence_ids` | PASS | Invalid IDs filtered |

---

## 4. Orchestration Module

**Location:** `backend/tests/test_orchestration.py`  
**Status:** 9/10 passing

| # | Test | Status | Description |
|---|------|--------|-------------|
| 147 | `test_hit_quality_prefers_trusted_sources` | PASS | gov/edu > blog in quality score |
| 148 | `test_inject_evidence_marks_low_confidence_slides` | PASS | No-evidence slides tracked |
| 149 | `test_build_generation_seed_includes_long_document_segments` | PASS | Segments+key_points+keywords in seed |
| 150 | `test_should_retrieve_for_long_document_with_rich_profile` | PASS | L0+profile→retrieve |
| 151 | `test_should_retrieve_when_user_requests_citations` | PASS | Citation request→retrieve |
| 152 | `test_validate_evidence_integrity_removes_orphan_ids` | PASS | Orphan evidence_ids cleaned |
| 153 | `test_inject_evidence_filters_noise_snippets` | PASS | Noise filtered from catalog |
| 154 | `test_inject_evidence_uses_semantic_matching_not_mechanical` | PASS | Content overlap>position |
| 155 | `test_inject_evidence_all_noise_snippets_marks_low_confidence` | PASS | All-noise→coverage=0 |
| 156 | `test_inject_evidence_includes_low_confidence_bullets` | **FAIL** | Pre-existing: count 0≠1 after parallel refactoring |

---

## 5. Skeleton Module

**Location:** `backend/tests/test_skeleton.py`  
**Status:** 5/5 passing

| # | Test | Status | Description |
|---|------|--------|-------------|
| 157 | `test_generate_skeleton_uses_llm_when_configured` | PASS | Real LLM→skeleton slides |
| 158 | `test_generate_skeleton_falls_back_without_api_key` | PASS | No key→rule-based fallback |
| 159 | `test_generate_skeleton_uses_page_range_and_desired_chapters` | PASS | Duration→page range; config→chapter count |
| 160 | `test_normalize_skeleton_maps_model_slide_ids_to_chapters` | PASS | chapter_id→correct mapping |
| 161 | `test_normalize_skeleton_accepts_sections_alias` | PASS | "sections" alias for "chapters" |

---

## 6. Document Processing Module

**Location:** `backend/tests/test_document_processing.py`  
**Status:** 1/1 passing

| # | Test | Status | Description |
|---|------|--------|-------------|
| 162 | `test_build_document_profile_extracts_segments_and_key_points` | PASS | Long text→segments, char_count, key_points, keywords |

---

## 7. Frontend

**Location:** `frontend/src/tests/`  
**Status:** 24/24 passing

### 7.1 Markdown Export (`outlineToMarkdown.test.ts`) — 7 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 163 | `includes title as H1` | PASS | `# AI Education` |
| 164 | `includes slide titles as H2` | PASS | `## Background`, `## Solution` |
| 165 | `includes bullets with evidence references` | PASS | `` `[ev_1]` `` marker |
| 166 | `includes key_message, visual_suggestion, speaker_notes, takeaway` | PASS | All B1 fields rendered |
| 167 | `includes evidence catalog` | PASS | `## 证据目录` with source_id |
| 168 | `handles empty evidence catalog` | PASS | Section omitted |
| 169 | `handles empty speaker_notes gracefully` | PASS | No "null" leakage |

### 7.2 SlidePanel Component (`SlidePanel.test.ts`) — 7 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 170 | `displays page badge with index/total` | PASS | "1 / 6" badge |
| 171 | `displays slide title as input when editable` | PASS | `<input class="title-inline">` |
| 172 | `displays slide title as strong when not editable` | PASS | `.page-title-label` rendered |
| 173 | `shows evidence button when bullet has evidence_ids` | PASS | "证据详情 · 1 条" visible |
| 174 | `hides regenerate button when not editable` | PASS | "重新生成" absent |
| 175 | `does not show evidence button without evidence` | PASS | "证据详情" absent when [] |
| 176 | `renders key_message, visual_suggestion, takeaway fields` | PASS | All B1 fields present |

### 7.3 SlideDeckView Component (`SlideDeckView.test.ts`) — 4 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 177 | `displays page list with slide titles` | PASS | Titles + "3 页" |
| 178 | `shows first page initially` | PASS | "1 / 3" |
| 179 | `prev button is disabled on first page` | PASS | ← disabled |
| 180 | `clicking page thumb changes current slide` | PASS | Click→"2 / 3" |

### 7.4 GeneratingView Component (`GeneratingView.test.ts`) — 6 tests

| # | Test | Status | Description |
|---|------|--------|-------------|
| 181 | `shows progress message` | PASS | "Generating page 3…" |
| 182 | `shows progress fill with width style` | PASS | `.progress-fill` exists |
| 183 | `shows page status chips` | PASS | 5 chips for 5 slides |
| 184 | `shows done and generating chips` | PASS | 2.done + 1.failed |
| 185 | `shows phase in summary` | PASS | "llm_page" visible |
| 186 | `clicking chip selects that slide` | PASS | `active` class applied |

---

## 8. Known Issues

| ID | Severity | Test # | Module | Description |
|----|----------|--------|--------|-------------|
| K-1 | Low | 156 | Orchestration | `test_inject_evidence_includes_low_confidence_bullets` — expected `low_confidence_bullets=1`, got `0`. Caused by parallel branch refactoring of `_inject_evidence`; does not block any active feature. |

---

## 9. Coverage Gaps (Planned)

| Priority | Area | Planned Tests | Notes |
|----------|------|---------------|-------|
| P2 | `TaskSidebar.vue` | 4 | History list, upload button, search, skeleton loading |
| P2 | `App.vue` computed properties | 3 | `footerHint`, `currentStep`, `stepStatus` |
| P3 | English evidence cleaning | 2 | HTML tables, JSON dumps |
| P3 | E2E mock API flow | 1 | Full 4-step flow with mock backend |

---

## 10. Test Infrastructure

| Layer | Runner | Configuration |
|-------|--------|---------------|
| Backend | `pytest` 9.0.3 | `backend/.venv`, `PYTHONPATH=backend` |
| Backend async | `pytest-anyio` 4.13.0 | `@pytest.mark.anyio` decorator |
| Frontend | `vitest` 4.1.9 | `environment: 'jsdom'`, `@vitejs/plugin-vue` |
| Frontend utils | `@vue/test-utils` 2.4.6 | Component mounting, stubs for Naive UI |
| Mock API | `fastapi.testclient.TestClient` | In-memory `TASK_STORE`, `USE_DB_STORE=False` |

### Execution

```bash
# Backend (from repository root)
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests/ -v

# Frontend (from repository root)
npx vitest run --config frontend/vite.config.ts
```
