import logging
import os
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from reality_defender_slack_app.config import Settings, get_settings, setup_logging

REQUIRED = {
    "SLACK_CLIENT_ID": "123.456",
    "SLACK_CLIENT_SECRET": "client-secret",
    "SLACK_SIGNING_SECRET": "signing-secret",
}


def test_settings_with_required_fields() -> None:
    """Settings load from explicit values with sensible defaults."""
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        slack_client_id="123.456",
        slack_client_secret="client-secret",
        slack_signing_secret="signing-secret",
    )

    assert settings.slack_client_id == "123.456"
    assert settings.slack_signing_secret == "signing-secret"
    assert settings.log_level == "INFO"  # default
    assert settings.port == 3000  # default
    assert settings.allow_shared_rd_key is False  # default


def test_settings_missing_required_raises() -> None:
    """Missing required Slack credentials raise a validation error."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


@patch.dict(os.environ, {**REQUIRED, "LOG_LEVEL": "ERROR", "PORT": "8080"})
def test_get_settings_reads_environment() -> None:
    """get_settings reads from the process environment."""
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.slack_client_id == "123.456"
    assert settings.log_level == "ERROR"
    assert settings.port == 8080


@patch("reality_defender_slack_app.config.logging.basicConfig")
def test_setup_logging_default_level(mock_basic_config: MagicMock) -> None:
    """Test setup_logging with default INFO level."""
    setup_logging()

    mock_basic_config.assert_called_once_with(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@patch("reality_defender_slack_app.config.logging.basicConfig")
def test_setup_logging_invalid_level(mock_basic_config: MagicMock) -> None:
    """Test setup_logging with invalid level defaults to INFO."""
    setup_logging("INVALID")

    mock_basic_config.assert_called_once_with(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@patch("reality_defender_slack_app.config.logging.getLogger")
def test_setup_logging_configures_specific_loggers(mock_get_logger: MagicMock) -> None:
    """Test that specific loggers are configured."""
    mock_slack_logger = MagicMock()
    mock_aiohttp_logger = MagicMock()

    def side_effect(name: str) -> MagicMock:
        if name == "slack_bolt":
            return mock_slack_logger
        elif name == "aiohttp":
            return mock_aiohttp_logger
        return MagicMock()

    mock_get_logger.side_effect = side_effect

    setup_logging()

    mock_slack_logger.setLevel.assert_called_once_with(logging.WARNING)
    mock_aiohttp_logger.setLevel.assert_called_once_with(logging.WARNING)
