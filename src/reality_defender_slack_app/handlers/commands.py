from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from slack_bolt.app.async_app import AsyncApp

from reality_defender_slack_app.background import spawn
from reality_defender_slack_app.deps import Deps
from reality_defender_slack_app.services.analysis import analyze_url_and_post
from reality_defender_slack_app.services.keys import (
    SETUP_REQUIRED_MESSAGE,
    resolve_api_key,
)

logger = logging.getLogger(__name__)

SOCIAL_MEDIA_DOMAINS = {
    "youtube.com",
    "youtu.be",
    "twitter.com",
    "x.com",
    "instagram.com",
    "facebook.com",
    "fb.com",
    "tiktok.com",
}


def register_command_handlers(app: AsyncApp, deps: Deps) -> None:
    @app.command("/detect")
    async def handle_detect(
        ack: Any, command: Any, client: Any, context: Any, respond: Any
    ) -> None:
        await ack()

        url = command.get("text", "").strip()
        channel_id = command["channel_id"]
        team_id = context.get("team_id")
        user_id = command.get("user_id")

        if not url:
            await respond("Please provide a URL to analyze: `/detect <url>`")
            return

        domain = urlparse(url).netloc.lower().removeprefix("www.")
        is_social = any(domain == d or domain.endswith("." + d) for d in SOCIAL_MEDIA_DOMAINS)
        if not is_social:
            supported = ", ".join(f"`{d}`" for d in sorted(SOCIAL_MEDIA_DOMAINS))
            await respond(f"Unsupported social media link `{url}`. Supported: {supported}")
            return

        api_key = await resolve_api_key(deps.key_store, team_id, deps.settings)
        if not api_key:
            await respond(SETUP_REQUIRED_MESSAGE)
            return

        # This message becomes the thread parent — result posts as a reply.
        msg = await client.chat_postMessage(
            channel=channel_id,
            text=f":hourglass_flowing_sand: Analyzing `{url}`...",
        )

        spawn(
            analyze_url_and_post(
                client=client,
                rd_client=deps.rd_client,
                tracker=deps.tracker,
                api_key=api_key,
                team_id=team_id or "",
                user_id=user_id or "",
                channel_id=channel_id,
                thread_ts=msg["ts"],
                url=url,
            )
        )

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

    @app.command("/analysis-status")
    async def handle_status(ack: Any, command: Any, context: Any, respond: Any) -> None:
        await ack()

        team_id = context.get("team_id") or ""
        user_id = command.get("user_id") or ""
        records = deps.tracker.for_user(team_id, user_id)

        if not records:
            await respond("You have no analyses in progress.")
            return

        lines = [f"• `{r.label}` — {r.status}" for r in records]
        await respond("Your analyses:\n" + "\n".join(lines))
