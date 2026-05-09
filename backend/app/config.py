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
    task_schema_version: str = "v0.2.0"
    outline_schema_version: str = "v0.2.0"
    retrieval_min_evidence_per_slide: int = 1
    retrieval_min_quality_score: float = 0.45
    retrieval_enable_fallback_deepen: bool = True


settings = Settings()
