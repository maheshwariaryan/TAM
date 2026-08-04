import base64
from pathlib import Path

from pydantic import field_validator
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
        # Without this, pydantic v2 skips validators for fields that fall back
        # to their default (e.g. FILE_ENCRYPTION_KEY simply not set in .env) —
        # we want a clear startup error in that case, not a silent b""/"" default.
        validate_default=True,
    )

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    use_mock_llm: bool = True  # Default True: full pipeline works without an API key

    # Storage — relative to wherever the server is launched from
    deal_store_dir: Path = Path("data/deals")
    upload_dir: Path = Path("data/uploads")
    processed_dir: Path = Path("data/processed")
    user_store_dir: Path = Path("data/users")
    notes_dir: Path = Path("data/notes")
    inquiries_dir: Path = Path("data/inquiries")

    # Security — at-rest file encryption + JWT session tokens.
    #
    # FILE_ENCRYPTION_KEY is the AES-256-GCM master key for every file this app
    # persists (deal/user JSON, uploaded documents, processed pipeline output).
    # Set it in .env as a base64-encoded 32-byte value, e.g.:
    #   python -c "import base64, os; print(base64.b64encode(os.urandom(32)).decode())"
    # This is a POC-grade master key held directly in an env var. Before any real
    # production use, this must move to a real KMS/Vault (AWS KMS, GCP KMS,
    # HashiCorp Vault, etc.) — key-loading is isolated to this one settings
    # field, so swapping the source later doesn't touch any call site that
    # uses `settings.file_encryption_key`.
    file_encryption_key: bytes = b""
    # JWT_SECRET_KEY signs session tokens (HS256). Any sufficiently random
    # string works; generate with e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
    jwt_secret_key: str = ""
    jwt_expiry_days: int = 7

    @field_validator("file_encryption_key", mode="before")
    @classmethod
    def _decode_file_encryption_key(cls, v: str | bytes) -> bytes:
        if isinstance(v, bytes):
            return v
        if not v:
            raise ValueError(
                "FILE_ENCRYPTION_KEY is not set. Generate one with: "
                "python -c \"import base64, os; print(base64.b64encode(os.urandom(32)).decode())\" "
                "and set it in .env / backend/.env.local."
            )
        try:
            decoded = base64.b64decode(v, validate=True)
        except Exception as exc:
            raise ValueError("FILE_ENCRYPTION_KEY must be valid base64.") from exc
        if len(decoded) != 32:
            raise ValueError(
                f"FILE_ENCRYPTION_KEY must decode to exactly 32 bytes (AES-256), got {len(decoded)}."
            )
        return decoded

    @field_validator("jwt_secret_key")
    @classmethod
    def _check_jwt_secret_key(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError(
                "JWT_SECRET_KEY is not set (or too short — need >=32 chars). Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(32))\" "
                "and set it in .env / backend/.env.local."
            )
        return v

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
settings.user_store_dir.mkdir(parents=True, exist_ok=True)
settings.notes_dir.mkdir(parents=True, exist_ok=True)
settings.inquiries_dir.mkdir(parents=True, exist_ok=True)
