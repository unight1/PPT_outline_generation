from __future__ import annotations

from app.services import orchestration


def test_hit_quality_prefers_trusted_sources() -> None:
    low = orchestration._hit_quality(
        {"score": 0.9, "confidence": 0.8, "source_id": "random_blog_post", "locator": "L1", "snippet": "x"}
    )
    high = orchestration._hit_quality(
        {"score": 0.7, "confidence": 0.7, "source_id": "official_gov_report", "locator": "L1", "snippet": "x"}
    )
    assert high > low


def test_inject_evidence_marks_low_confidence_slides() -> None:
    outline = {
        "title": "T",
        "slides": [
            {
                "slide_id": "s1",
                "title": "有证据页",
                "bullets": [{"bullet_id": "s1-b1", "text": "x", "evidence_ids": []}],
                "speaker_notes": "",
            },
            {
                "slide_id": "s2",
                "title": "无证据页",
                "bullets": [{"bullet_id": "s2-b1", "text": "y", "evidence_ids": []}],
                "speaker_notes": "",
            },
        ],
        "evidence_catalog": [],
        "meta": {},
    }
    retrieval = {
        "有证据页": [{"source_id": "official", "locator": "L1", "snippet": "abc", "score": 0.8, "confidence": 0.8}],
        "无证据页": [],
    }
    enriched = orchestration._inject_evidence(outline=outline, retrieval_by_slide=retrieval, min_evidence_per_slide=1)
    assert enriched["meta"]["evidence_coverage_total"] >= 1
    assert "无证据页" in enriched["meta"]["low_confidence_slides"]


def test_build_generation_seed_includes_long_document_segments() -> None:
    seed = orchestration._build_generation_seed(
        topic="医疗 AI",
        source_type="long_document",
        document_text=None,
        document_title="白皮书",
        raw_notes=None,
        document_summary="摘要内容",
        document_segments=["第一段关于诊断。", "第二段关于手术机器人。"],
        document_key_points=["诊断流程变化。", "机器人提升精准度。"],
        document_keywords=["诊断", "机器人"],
    )
    assert "文档分段" in seed
    assert "第一段关于诊断" in seed
    assert "文档要点" in seed
    assert "关键词" in seed


def test_should_retrieve_for_long_document_with_rich_profile() -> None:
    assert orchestration._should_retrieve(
        retrieval_depth="L0",
        clarification={"submitted": False},
        raw_notes=None,
        source_type="long_document",
        document_profile={"char_count": 1200},
    )


def test_should_retrieve_when_user_requests_citations() -> None:
    assert orchestration._should_retrieve(
        retrieval_depth="L0",
        clarification={"submitted": True, "questions": []},
        raw_notes="请补充可引用资料来源",
        source_type="short_topic",
        document_profile=None,
    )


def test_validate_evidence_integrity_removes_orphan_ids() -> None:
    outline = {
        "title": "T",
        "slides": [
            {
                "slide_id": "s1",
                "title": "页1",
                "bullets": [{"bullet_id": "s1-b1", "text": "x", "evidence_ids": ["ev_1", "ev_missing"]}],
                "speaker_notes": "",
            }
        ],
        "evidence_catalog": [
            {
                "evidence_id": "ev_1",
                "snippet": "a",
                "source_id": "s",
                "locator": "L1",
            }
        ],
        "meta": {},
    }
    fixed = orchestration._validate_evidence_integrity(outline)
    bullet_ids = fixed["slides"][0]["bullets"][0]["evidence_ids"]
    assert bullet_ids == ["ev_1"]
    assert fixed["meta"]["evidence_integrity_ok"] is True
    assert fixed["meta"]["evidence_orphaned_refs_removed"] == 1


# ── R1+R2: _inject_evidence with cleaning + matching ────────


def test_inject_evidence_filters_noise_snippets() -> None:
    outline = {
        "title": "T",
        "slides": [
            {
                "slide_id": "s1",
                "title": "页1",
                "bullets": [{"bullet_id": "s1-b1", "text": "AI市场规模", "evidence_ids": []}],
                "speaker_notes": "",
            }
        ],
        "evidence_catalog": [],
        "meta": {},
    }
    retrieval = {
        "页1": [
            {"source_id": "noise", "locator": "L1", "snippet": "网站地图", "score": 0.9, "confidence": 0.8},
            {"source_id": "real", "locator": "L2", "snippet": "AI教育市场规模达60亿美元", "score": 0.85, "confidence": 0.7},
        ],
    }
    enriched = orchestration._inject_evidence(outline=outline, retrieval_by_slide=retrieval, min_evidence_per_slide=1)
    catalog = enriched["evidence_catalog"]
    # Noise snippet should be filtered out
    snippets = [ev["snippet"] for ev in catalog]
    assert "网站地图" not in snippets
    assert any("AI教育" in s for s in snippets)


def test_inject_evidence_uses_semantic_matching_not_mechanical() -> None:
    outline = {
        "title": "T",
        "slides": [
            {
                "slide_id": "s1",
                "title": "页1",
                "bullets": [
                    {"bullet_id": "s1-b1", "text": "微服务架构优势", "evidence_ids": []},
                    {"bullet_id": "s1-b2", "text": "AI市场规模", "evidence_ids": []},
                ],
                "speaker_notes": "",
            }
        ],
        "evidence_catalog": [],
        "meta": {},
    }
    retrieval = {
        "页1": [
            {"source_id": "r1", "locator": "L1", "snippet": "AI教育市场规模达60亿美元", "score": 0.9, "confidence": 0.8},
            {"source_id": "r2", "locator": "L2", "snippet": "微服务架构提升了可扩展性", "score": 0.85, "confidence": 0.7},
        ],
    }
    enriched = orchestration._inject_evidence(outline=outline, retrieval_by_slide=retrieval, min_evidence_per_slide=1)
    bullets = enriched["slides"][0]["bullets"]
    # b1 "微服务架构优势" should match r2, b2 "AI市场规模" should match r1
    # Not mechanical: b1→ev_1, b2→ev_2
    assert bullets[0]["evidence_ids"] != ["ev_1"] or bullets[1]["evidence_ids"] != ["ev_2"]  # not both mechanical
    # Verify semantic: b1 should get the 微服务 evidence
    assert bullets[0]["evidence_ids"] == ["ev_2"], f"Expected ev_2 (微服务) for b1, got {bullets[0]['evidence_ids']}"
    assert bullets[1]["evidence_ids"] == ["ev_1"], f"Expected ev_1 (AI) for b2, got {bullets[1]['evidence_ids']}"


def test_inject_evidence_all_noise_snippets_marks_low_confidence() -> None:
    outline = {
        "title": "T",
        "slides": [
            {
                "slide_id": "s1",
                "title": "页1",
                "bullets": [{"bullet_id": "s1-b1", "text": "需要证据的要点", "evidence_ids": []}],
                "speaker_notes": "",
            }
        ],
        "evidence_catalog": [],
        "meta": {},
    }
    retrieval = {
        "页1": [
            {"source_id": "n1", "locator": "L1", "snippet": "网站地图", "score": 0.9},
            {"source_id": "n2", "locator": "L2", "snippet": "Copyright", "score": 0.8},
        ],
    }
    enriched = orchestration._inject_evidence(outline=outline, retrieval_by_slide=retrieval, min_evidence_per_slide=1)
    # All snippets filtered → no evidence added → slide marked low_confidence
    assert "页1" in enriched["meta"]["low_confidence_slides"]
    assert enriched["meta"]["evidence_coverage_total"] == 0


def test_inject_evidence_includes_low_confidence_bullets() -> None:
    outline = {
        "title": "T",
        "slides": [
            {
                "slide_id": "s1",
                "title": "页1",
                "bullets": [
                    {"bullet_id": "s1-b1", "text": "AI市场规模", "evidence_ids": []},
                    {"bullet_id": "s1-b2", "text": "无关内容", "evidence_ids": []},
                ],
                "speaker_notes": "",
            }
        ],
        "evidence_catalog": [],
        "meta": {},
    }
    retrieval = {
        "页1": [
            {"source_id": "r1", "locator": "L1", "snippet": "AI教育市场规模达60亿美元", "score": 0.9},
        ],
    }
    enriched = orchestration._inject_evidence(outline=outline, retrieval_by_slide=retrieval, min_evidence_per_slide=1)
    assert "low_confidence_bullets" in enriched["meta"]
    # High-quality evidence (score 0.9 ≥ 0.5) triggers fallback assignment even for
    # low-overlap bullets; both bullets receive evidence via quality fallback
    assert enriched["meta"]["low_confidence_bullets"] == 0
