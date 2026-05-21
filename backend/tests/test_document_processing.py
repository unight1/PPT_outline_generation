from __future__ import annotations

from app.services.document_processing import build_document_profile


def test_build_document_profile_extracts_segments_and_key_points() -> None:
    text = "人工智能正在改变医疗诊断流程。" * 30 + "手术机器人可提升精准度。" * 20
    profile = build_document_profile(text)
    assert profile is not None
    assert profile["segment_count"] >= 2
    assert len(profile["segments"]) >= 2
    assert len(profile["key_points"]) >= 1
    assert isinstance(profile["keywords"], list)
