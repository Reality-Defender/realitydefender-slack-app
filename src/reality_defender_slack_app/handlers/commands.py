from __future__ import annotations

import logging
from typing import Any

from slack_bolt.app.async_app import AsyncApp

from reality_defender_slack_app.deps import Deps

logger = logging.getLogger(__name__)


def register_command_handlers(app: AsyncApp, deps: Deps) -> None:
    @app.command("/setup-rd")
    async def handle_setup_rd(ack: Any, command: Any, context: Any, respond: Any) -> None:
        await ack()

        api_key = command.get("text", "").strip()
        team_id = context.get("team_id")

        if not api_key:
            await respond("Usage: `/setup-rd <your Reality Defender API key>`")
            return
        if not team_id:
            await respond(":x: Could not determine your workspace. Please try again.")
            return

        await deps.key_store.set(team_id, api_key)
        await respond(":white_check_mark: Reality Defender API key saved for this workspace.")
