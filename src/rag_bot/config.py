from functools import lru_cache
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Preserve container / shell overrides before .env reload.
_PRESERVED_ENV_KEYS = (
    "DATABASE_URL",
    "ANTHROPIC_API_KEY",
    "VOYAGE_API_KEY",
    "ANTHROPIC_MODEL",
    "GROUNDING_THRESHOLD",
)
_preserved_env = {key: os.environ[key] for key in _PRESERVED_ENV_KEYS if os.environ.get(key)}
load_dotenv(PROJECT_ROOT / ".env", override=True)
for key, value in _preserved_env.items():
    os.environ[key] = value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    anthropic_api_key: str = ""
    voyage_api_key: str = ""
    database_url: str = "postgresql://rag:rag@localhost:5433/rag_bot"
    anthropic_model: str = "claude-sonnet-4-6"
    grounding_threshold: float = 0.35
    retrieval_top_k: int = 20
    retrieval_top_parents: int = 3
    session_inactivity_hours: int = 24
    session_state_token_threshold: int = 5000
    learnings_retention_seconds: int = 3600


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reload_settings() -> Settings:
    get_settings.cache_clear()
    return get_settings()
