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

    # Reality Defender: optional shared key for LOCAL DEV ONLY. It is used as a
    # fallback only when set; in production leave it unset so each workspace must
    # supply its own key via /setup-rd and a missing key never silently bills the
    # operator's account.
    reality_defender_api_key: str | None = None

    # AWS / DynamoDB durable storage. When the table names below are set,
    # create_app uses DynamoDB-backed stores; otherwise it falls back to
    # ephemeral in-memory / file stores so local dev needs no AWS.
    aws_region: str | None = None
    dynamodb_installations_table: str | None = None
    dynamodb_oauth_states_table: str | None = None
    dynamodb_rd_keys_table: str | None = None
    # KMS key that encrypts RD API keys at the application layer before they are
    # written to DynamoDB. Required when dynamodb_rd_keys_table is set.
    rd_key_kms_key_id: str | None = None

    log_level: str = "INFO"
    port: int = 3000

    @property
    def dynamodb_enabled(self) -> bool:
        """True when all DynamoDB tables are configured (production mode)."""
        return bool(
            self.dynamodb_installations_table
            and self.dynamodb_oauth_states_table
            and self.dynamodb_rd_keys_table
        )


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
