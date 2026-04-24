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
    llm_model: str = "deepseek-r1-671b"
    llm_timeout_seconds: float = 45.0
    openai_api_key: str | None = None
    openai_base_url: str | None = None


settings = Settings()
