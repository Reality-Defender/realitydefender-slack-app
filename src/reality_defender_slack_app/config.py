from __future__ import annotations

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration for the Slack bot, loaded from the environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Slack app credentials for multi-workspace OAuth.
    slack_client_id: str
    slack_client_secret: str
    slack_signing_secret: str

    # Reality Defender: optional shared key for local dev only. In production
    # each workspace supplies its own key; this is only used when
    # allow_shared_rd_key is true (see the per-workspace key store, Phase C).
    reality_defender_api_key: str | None = None
    allow_shared_rd_key: bool = False

    log_level: str = "INFO"
    port: int = 3000


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (env read once per process)."""
    return Settings()  # type: ignore[call-arg]  # values come from the environment


def setup_logging(log_level: str = "INFO") -> None:
    """
    Setup logging configuration.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    level = level_map.get(log_level.upper(), logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Set specific loggers
    logging.getLogger("slack_bolt").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
