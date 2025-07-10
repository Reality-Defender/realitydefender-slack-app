# main.py
from __future__ import annotations

import asyncio
import signal
import sys
from types import FrameType
from typing import Optional

import logging

from slack_app.app import App
from slack_app.config import setup_logging, load_config

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
    config = load_config()

    # Setup logging
    setup_logging(config.log_level)

    # Create and start our Slack bot
    slack_app: App = App(
        slack_bot_token=config.slack_bot_token,
        slack_app_token=config.slack_app_token,
    )

    logger.info("Starting Slack application...")

    # Start the long polling.
    asyncio.create_task(slack_app.poll_results())

    # Start listening.
    asyncio.create_task(slack_app.start())

    # Keep the application running
    while True:
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
