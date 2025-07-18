import os
import logging
from pydantic import BaseModel, Field


from dotenv import load_dotenv

load_dotenv()


class Config(BaseModel):
    """Configuration management for the Slack bot."""

    # Slack configuration
    slack_bot_token: str = Field(
        alias="SLACK_BOT_TOKEN",
        description="Token for the Slack bot user.",
    )

    slack_app_token: str = Field(
        alias="SLACK_APP_TOKEN",
        description="Token for the Slack app.",
    )

    # Application configuration
    log_level: str = Field("INFO", alias="LOG_LEVEL", description="Current log level")


def load_config(env: dict[str, str] | None = None) -> Config:
    env = env or dict(os.environ)

    return Config.model_validate(env)


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
