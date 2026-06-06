from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> parents[1] = backend/, parents[2] = repo root
_BACKEND_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            _REPO_ROOT / ".env",
            _BACKEND_DIR / ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str | None = None
    redis_url: str | None = None
    use_real_llm: bool = False
    llm_model: str = "deepseek-v4-flash"
    llm_timeout_seconds: float = 45.0
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    tavily_api_key: str | None = None
    retrieval_documents_dir: str = "sample_docs"
    retrieval_chroma_dir: str = "./chroma_data"
    generation_worker_max_workers: int = 2
    generation_max_retries: int = 2
    # Must exceed generation_hard_timeout_seconds so restarts do not treat long jobs as stale.
    recovery_stale_generating_seconds: int = 4200
    # First-time HF model download + CPU embed/rerank can exceed a few minutes; override via env.
    generation_hard_timeout_seconds: int = 3600
    # Load embedding/reranker singleton in a background thread so downloads run outside generate().
    retrieval_warmup_on_startup: bool = True
    task_schema_version: str = "v1.1.0"
    outline_schema_version: str = "v1.1.0"
    retrieval_min_evidence_per_slide: int = 1
    retrieval_min_quality_score: float = 0.45
    # A1: default off — secondary depth expansion adds latency and is rarely needed.
    retrieval_enable_fallback_deepen: bool = False
    # A1: max concurrent page retrievals (asyncio.gather). Keep ≤ 3 to avoid OOM on CPU.
    retrieval_parallel_pages: int = 3
    # A1: allow Tavily web search at all (requires TAVILY_API_KEY).
    retrieval_tavily_enabled: bool = True
    # A1: limit Tavily calls per generate run; 0 = unlimited (not recommended).
    retrieval_tavily_max_pages: int = 2
    retrieval_default_source_quality: str = "medium"
    task_documents_dir: str = "./task_documents"
    task_documents_chroma_dir: str = "./task_chroma_data"
    task_document_upload_max_bytes: int = 2_000_000


settings = Settings()