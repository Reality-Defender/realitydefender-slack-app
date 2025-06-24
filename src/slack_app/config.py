import os
import logging

from dotenv import load_dotenv

load_dotenv()

class Config:
    """Configuration management for the Slack bot."""

    # Slack configuration
    SLACK_BOT_TOKEN: str = os.getenv("SLACK_BOT_TOKEN", "")
    SLACK_APP_TOKEN: str = os.getenv("SLACK_APP_TOKEN", "")

    # Application configuration
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def validate(cls) -> None:
        """Validate required configuration."""
        required_vars = [
            ("SLACK_BOT_TOKEN", cls.SLACK_BOT_TOKEN),
            ("SLACK_APP_TOKEN", cls.SLACK_APP_TOKEN),
        ]

        missing_vars = [var_name for var_name, var_value in required_vars if not var_value]

        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    @classmethod
    def get_log_level(cls) -> int:
        """Get logging level from configuration."""
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL,
        }
        return level_map.get(cls.LOG_LEVEL.upper(), logging.INFO)


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
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Set specific loggers
    logging.getLogger("slack_bolt").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)