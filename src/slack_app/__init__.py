# main.py
from __future__ import annotations

import asyncio
import signal
import sys
from types import FrameType
from typing import Optional

import logging

from slack_app.app import App
from slack_app.config import Config, setup_logging

logger = logging.getLogger(__name__)


def signal_handler(signum: int, _frame: Optional[FrameType]) -> None:
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}")
    sys.exit(0)


async def main() -> None:
    """Main application entry point"""
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Validate configuration
    Config.validate()

    # Setup logging
    setup_logging(Config.LOG_LEVEL)

    # Create and start our Slack bot
    slack_bot: App = App(
        slack_bot_token=Config.SLACK_BOT_TOKEN,
        slack_app_token=Config.SLACK_APP_TOKEN,
    )

    logger.info("Starting Slack bot application...")

    # Start the long polling.
    asyncio.create_task(slack_bot.poll_results())

    # Start listening.
    asyncio.create_task(slack_bot.start())

    # Keep the application running
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
