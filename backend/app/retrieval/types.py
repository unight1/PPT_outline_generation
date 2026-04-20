from enum import Enum

from pydantic import BaseModel


class RetrievalDepth(str, Enum):
    """检索深度档位，与 API 契约 §1.3 对齐。"""

    L0 = "L0"  # 轻量，少召回、低延迟
    L1 = "L1"  # 默认平衡
    L2 = "L2"  # 深度，多召回、可加重排


class RetrievalHit(BaseModel):
    """单条检索结果，与 API 契约 §4 RetrievalHit 形状对齐。"""

    snippet: str
    source_id: str
    locator: str
    score: float | None = None
    confidence: float | None = None


class RetrievalRequest(BaseModel):
    """检索请求。"""

    query: str
    depth: RetrievalDepth = RetrievalDepth.L1
    source_filter: list[str] | None = None
    max_results: int | None = None


class RetrievalResult(BaseModel):
    """检索结果。"""

    hits: list[RetrievalHit]
    depth: RetrievalDepth
    latency_ms: float


class DocumentChunk(BaseModel):
    """文档分块，内部使用，不对外暴露。"""

    content: str
    source_id: str
    locator: str


class IndexMatch(BaseModel):
    """向量索引匹配结果，内部使用。"""

    chunk_index: int
    score: float
