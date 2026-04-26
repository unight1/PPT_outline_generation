from dataclasses import dataclass

from app.retrieval.types import RetrievalDepth


@dataclass(frozen=True)
class DepthProfile:
    """单个深度档位的参数集合。"""

    max_recall: int
    enable_reranking: bool
    rerank_top_k: int
    timeout_seconds: float
    min_score_threshold: float


DEPTH_PROFILES: dict[RetrievalDepth, DepthProfile] = {
    RetrievalDepth.L0: DepthProfile(
        max_recall=5,
        enable_reranking=False,
        rerank_top_k=5,
        timeout_seconds=5.0,
        min_score_threshold=0.3,
    ),
    RetrievalDepth.L1: DepthProfile(
        max_recall=15,
        enable_reranking=False,
        rerank_top_k=10,
        timeout_seconds=10.0,
        min_score_threshold=0.2,
    ),
    RetrievalDepth.L2: DepthProfile(
        max_recall=30,
        enable_reranking=True,
        rerank_top_k=10,
        timeout_seconds=20.0,
        min_score_threshold=0.1,
    ),
}


def get_depth_profile(depth: RetrievalDepth) -> DepthProfile:
    return DEPTH_PROFILES[depth]
