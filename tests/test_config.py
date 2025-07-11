import os
import logging
from unittest.mock import patch, MagicMock
from reality_defender_slack_app.config import Config, load_config, setup_logging


def test_config_with_required_fields() -> None:
    """Test Config creation with required fields."""
    config_data = {
        "SLACK_BOT_TOKEN": "xoxb-test-token",
        "SLACK_APP_TOKEN": "xapp-test-token",
    }
    config = Config.model_validate(config_data)

    assert config.slack_bot_token == "xoxb-test-token"
    assert config.slack_app_token == "xapp-test-token"
    assert config.log_level == "INFO"  # default value


def test_config_with_custom_log_level() -> None:
    """Test Config creation with custom log level."""
    config_data = {
        "SLACK_BOT_TOKEN": "xoxb-test-token",
        "SLACK_APP_TOKEN": "xapp-test-token",
        "LOG_LEVEL": "DEBUG",
    }
    config = Config.model_validate(config_data)

    assert config.log_level == "DEBUG"


def test_load_config_with_env_dict() -> None:
    """Test load_config with provided environment dictionary."""
    env_dict = {
        "SLACK_BOT_TOKEN": "xoxb-env-token",
        "SLACK_APP_TOKEN": "xapp-env-token",
        "LOG_LEVEL": "WARNING",
    }
    config = load_config(env_dict)

    assert config.slack_bot_token == "xoxb-env-token"
    assert config.slack_app_token == "xapp-env-token"
    assert config.log_level == "WARNING"


@patch.dict(
    os.environ,
    {
        "SLACK_BOT_TOKEN": "xoxb-os-token",
        "SLACK_APP_TOKEN": "xapp-os-token",
        "LOG_LEVEL": "ERROR",
    },
)
def test_load_config_from_os_environ() -> None:
    """Test load_config from os.environ."""
    config = load_config()

    assert config.slack_bot_token == "xoxb-os-token"
    assert config.slack_app_token == "xapp-os-token"
    assert config.log_level == "ERROR"


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
def test_setup_logging_debug_level(mock_basic_config: MagicMock) -> None:
    """Test setup_logging with DEBUG level."""
    setup_logging("DEBUG")

    mock_basic_config.assert_called_once_with(
        level=logging.DEBUG,
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

    def side_effect(name: str) -> MagicMock | None:
        if name == "slack_bolt":
            return mock_slack_logger
        elif name == "aiohttp":
            return mock_aiohttp_logger
        return MagicMock()

    mock_get_logger.side_effect = side_effect

    setup_logging()

    mock_slack_logger.setLevel.assert_called_once_with(logging.WARNING)
    mock_aiohttp_logger.setLevel.assert_called_once_with(logging.WARNING)


@patch("reality_defender_slack_app.config.logging.basicConfig")
def test_setup_logging_with_all_levels(mock_basic_config: MagicMock) -> None:
    """Test setup_logging with all valid levels."""
    levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    expected_levels = [
        logging.DEBUG,
        logging.INFO,
        logging.WARNING,
        logging.ERROR,
        logging.CRITICAL,
    ]

    for level, expected in zip(levels, expected_levels):
        mock_basic_config.reset_mock()
        setup_logging(level)
        mock_basic_config.assert_called_once_with(
            level=expected,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
