"""Application settings, loaded from the environment and an optional `.env` file."""

from __future__ import annotations

import ipaddress
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_SECRET_KEY = "dev-insecure-secret-key-change-me"  # noqa: S105 - sentinel, rejected in prod
MIN_PROD_SECRET_LENGTH = 32


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class ExtractorChoice(StrEnum):
    AUTO = "auto"
    RULES = "rules"
    CLAUDE = "claude"


class PipelineMode(StrEnum):
    INLINE = "inline"
    BACKGROUND = "background"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: Environment = Environment.DEV
    app_version: str = "0.1.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    database_url: str = "sqlite:///./jetstream.db"

    # Auth
    secret_key: SecretStr = SecretStr(DEFAULT_SECRET_KEY)
    access_token_ttl_min: int = Field(default=720, ge=1)
    cookie_name: str = "js_session"
    cookie_secure: bool = False
    invite_ttl_days: int = Field(default=7, ge=1)

    # Uploads and storage
    storage_dir: Path = Path("./storage")
    max_upload_mb: int = Field(default=15, ge=1)
    max_pdf_pages: int = Field(default=50, ge=1)
    # Email uploads: PDF attachments processed per email, and their total pages.
    max_attachments: int = Field(default=10, ge=0)
    max_total_pages: int = Field(default=200, ge=1)

    # Extraction
    extractor: ExtractorChoice = ExtractorChoice.AUTO
    anthropic_api_key: SecretStr | None = None
    claude_model: str = "claude-opus-5-5"
    claude_effort: Literal["low", "medium", "high", "max"] = "medium"
    claude_max_tokens: int = Field(default=16000, ge=1)
    claude_timeout_s: float = Field(default=120.0, gt=0)
    claude_max_retries: int = Field(default=2, ge=0)
    claude_server_fallback: bool = True

    # Pipeline and product behaviour
    pipeline_mode: PipelineMode = PipelineMode.INLINE
    # At startup, pending/processing documents idle this long are marked failed
    # (a restart drops queued background work) so they can be reprocessed.
    stale_document_minutes: int = Field(default=15, ge=1)
    public_app_url: str = "http://localhost:3001"
    default_review_threshold: int = Field(default=75, ge=50, le=100)
    share_link_ttl_days: int = Field(default=30, ge=1)

    # Rate limits: (attempts, window seconds)
    login_rate_limit: int = Field(default=10, ge=1)
    login_rate_window_s: int = Field(default=60, ge=1)
    public_rate_limit: int = Field(default=60, ge=1)
    public_rate_window_s: int = Field(default=60, ge=1)
    # Per account: after this many failed logins, each attempt waits a backoff
    # that doubles from 1 s up to `login_backoff_max_s` (short, so an attacker
    # cannot lock the owner out). A successful login clears it.
    login_backoff_after: int = Field(default=5, ge=1)
    login_backoff_max_s: int = Field(default=30, ge=1)

    # Proxies (IPs or CIDRs) whose X-Forwarded-For is believed when they are the
    # direct peer; the client IP keys rate limits and audit entries.
    trusted_proxies: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["127.0.0.1", "::1"]
    )

    # Comma-separated in the environment; empty disables CORS entirely.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _split_cors(cls, data: object) -> object:
        if isinstance(data, dict):
            for key in ("cors_origins", "CORS_ORIGINS", "trusted_proxies", "TRUSTED_PROXIES"):
                raw = data.get(key)
                if isinstance(raw, str):
                    data[key] = [o.strip() for o in raw.split(",") if o.strip()]
        return data

    @model_validator(mode="after")
    def _check_trusted_proxies(self) -> Settings:
        for entry in self.trusted_proxies:
            try:
                ipaddress.ip_network(entry, strict=False)
            except ValueError:
                raise ValueError(f"TRUSTED_PROXIES: {entry!r} is not an IP or CIDR") from None
        return self

    @model_validator(mode="after")
    def _check_production_secrets(self) -> Settings:
        if self.env is Environment.PROD:
            key = self.secret_key.get_secret_value()
            if key == DEFAULT_SECRET_KEY or len(key) < MIN_PROD_SECRET_LENGTH:
                raise ValueError(
                    "SECRET_KEY must be set to a unique value of at least "
                    f"{MIN_PROD_SECRET_LENGTH} characters in prod"
                )
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in prod")
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def claude_enabled(self) -> bool:
        """True when the Claude extractor should be the primary extractor."""
        if self.extractor is ExtractorChoice.RULES:
            return False
        return self.anthropic_api_key is not None and bool(
            self.anthropic_api_key.get_secret_value()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
