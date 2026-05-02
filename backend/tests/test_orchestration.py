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
