from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py lives at backend/app/config.py
_PROJECT_ROOT = Path(__file__).parent.parent.parent   # TAM/
_BACKEND_DIR  = Path(__file__).parent.parent           # TAM/backend/

# Load order: root .env first, then backend/.env.local (overrides, dev use only).
# backend/.env.local lets tooling toggle USE_MOCK_LLM without touching your .env.
_ENV_FILES = [str(_PROJECT_ROOT / ".env"), str(_BACKEND_DIR / ".env.local")]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILES,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-latest"
    use_mock_llm: bool = True  # Default True: full pipeline works without an API key

    # Storage — relative to wherever the server is launched from
    deal_store_dir: Path = Path("data/deals")
    upload_dir: Path = Path("data/uploads")
    processed_dir: Path = Path("data/processed")

    # Server
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    log_level: str = "INFO"
    log_json: bool = False  # set to true in production / cloud environments


settings = Settings()

# Ensure data directories exist on startup
settings.deal_store_dir.mkdir(parents=True, exist_ok=True)
settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.processed_dir.mkdir(parents=True, exist_ok=True)
