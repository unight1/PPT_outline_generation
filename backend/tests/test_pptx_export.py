from __future__ import annotations

import io

from app.services.pptx_export import export_outline_to_pptx


def test_export_minimal_outline():
    outline = {
        "title": "Test Outline",
        "slides": [
            {
                "slide_id": "s1",
                "title": "Slide 1",
                "bullets": [{"bullet_id": "s1-b1", "text": "Point A", "evidence_ids": []}],
                "speaker_notes": "Notes",
                "key_message": "Key",
            }
        ],
        "evidence_catalog": [],
        "chapters": [{"chapter_id": "ch1", "title": "Chapter 1", "slide_ids": ["s1"]}],
        "meta": {"retrieval_depth": "L1"},
    }
    pptx_bytes = export_outline_to_pptx(outline)
    assert isinstance(pptx_bytes, bytes)
    assert len(pptx_bytes) > 0


def test_export_multiple_slides():
    outline = {
        "title": "Multi-Slide",
        "slides": [
            {"slide_id": f"s{i}", "title": f"Slide {i}", "bullets": [
                {"bullet_id": f"s{i}-b1", "text": f"Point {i}", "evidence_ids": []}
            ], "speaker_notes": None}
            for i in range(1, 6)
        ],
        "evidence_catalog": [],
        "chapters": [],
        "meta": {},
    }
    pptx_bytes = export_outline_to_pptx(outline)
    assert len(pptx_bytes) > 5000  # Should produce substantial output


def test_export_no_chapters():
    outline = {
        "title": "No Chapters",
        "slides": [{"slide_id": "s1", "title": "T", "bullets": [], "speaker_notes": None}],
        "evidence_catalog": [],
        "chapters": [],
        "meta": {},
    }
    pptx_bytes = export_outline_to_pptx(outline)
    assert len(pptx_bytes) > 0


def test_export_handles_missing_fields():
    outline = {
        "title": "Minimal",
        "slides": [{"slide_id": "s1", "title": "", "bullets": [], "speaker_notes": None}],
        "evidence_catalog": [],
    }
    # Should not crash
    pptx_bytes = export_outline_to_pptx(outline)
    assert isinstance(pptx_bytes, bytes)
