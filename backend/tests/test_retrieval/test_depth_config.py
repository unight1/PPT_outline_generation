from app.retrieval.depth_config import DEPTH_PROFILES, get_depth_profile
from app.retrieval.types import RetrievalDepth


def test_all_depths_present():
    for depth in RetrievalDepth:
        assert depth in DEPTH_PROFILES


def test_l0_no_reranking():
    profile = get_depth_profile(RetrievalDepth.L0)
    assert profile.enable_reranking is False
    assert profile.max_recall == 5


def test_l1_balanced():
    profile = get_depth_profile(RetrievalDepth.L1)
    assert profile.enable_reranking is False
    assert profile.max_recall == 15


def test_l2_deep_with_reranking():
    profile = get_depth_profile(RetrievalDepth.L2)
    assert profile.enable_reranking is True
    assert profile.max_recall == 30


def test_recall_increases_with_depth():
    p0 = get_depth_profile(RetrievalDepth.L0)
    p1 = get_depth_profile(RetrievalDepth.L1)
    p2 = get_depth_profile(RetrievalDepth.L2)
    assert p0.max_recall < p1.max_recall < p2.max_recall


def test_threshold_decreases_with_depth():
    p0 = get_depth_profile(RetrievalDepth.L0)
    p2 = get_depth_profile(RetrievalDepth.L2)
    assert p0.min_score_threshold > p2.min_score_threshold
