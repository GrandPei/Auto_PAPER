"""Application settings using Pydantic Settings v2."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global application settings loaded from environment variables and .env file.

    All settings can be overridden via environment variables prefixed with PAPER_.
    """

    model_config = SettingsConfigDict(
        env_prefix="PAPER_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Storage ---
    download_dir: Path = Field(
        default=Path("./papers"),
        description="Directory where downloaded papers are stored",
    )
    cache_db: Path = Field(
        default=Path("./cache/papers.db"),
        description="Path to the SQLite cache database",
    )

    # --- API Keys ---
    openalex_email: str | None = Field(
        default=None,
        description="Email for OpenAlex polite pool (higher rate limits)",
    )
    semantic_scholar_api_key: str | None = Field(
        default=None,
        description="API key for Semantic Scholar (higher rate limits)",
    )
    unpaywall_email: str | None = Field(
        default=None,
        description="Email for Unpaywall API access",
    )

    # --- Download Settings ---
    download_timeout: int = Field(
        default=300,
        ge=10,
        le=3600,
        description="Download timeout in seconds",
    )
    download_max_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of download retry attempts",
    )
    download_concurrent_limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of concurrent downloads",
    )

    # --- Logging ---
    log_level: str = Field(
        default="INFO",
        pattern=r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
        description="Logging level",
    )
    log_file: str = Field(
        default="paper_downloader.log",
        description="Log file path",
    )


def get_settings() -> Settings:
    """Return a cached Settings instance.

    Returns:
        Settings: The application settings singleton.
    """
    return Settings()
