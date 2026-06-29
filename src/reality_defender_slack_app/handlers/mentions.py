from __future__ import annotations

import logging
from typing import Any

from slack_bolt.app.async_app import AsyncApp

from reality_defender_slack_app.background import spawn
from reality_defender_slack_app.deps import Deps
from reality_defender_slack_app.services.analysis import analyze_targets
from reality_defender_slack_app.services.keys import (
    SETUP_REQUIRED_MESSAGE,
    resolve_api_key,
)
from reality_defender_slack_app.services.media import collect_media, extract_social_url

logger = logging.getLogger(__name__)

USAGE_MESSAGE = (
    "Mention me with a supported social media link or attach a file, "
    "e.g. `@Reality Defender https://x.com/...` or `@Reality Defender` with a file."
)


def register_mention_handlers(app: AsyncApp, deps: Deps) -> None:
    @app.event("app_mention")
    async def handle_mention(event: Any, client: Any, context: Any, ack: Any) -> None:
        await ack()
        spawn(_process_mention(deps, client, context, event))


async def _process_mention(
    deps: Deps, client: Any, context: Any, event: dict[str, Any]
) -> None:
    channel_id = event["channel"]
    # Reply under the mention so results thread off the user's message.
    thread_ts = event.get("thread_ts") or event["ts"]
    team_id = context.get("team_id")

    try:
        api_key = await resolve_api_key(deps.key_store, team_id, deps.settings)
        if not api_key:
            await client.chat_postMessage(
                channel=channel_id, thread_ts=thread_ts, text=SETUP_REQUIRED_MESSAGE
            )
            return

        media = collect_media(event)
        url = extract_social_url(event.get("text", ""))

        if not media and not url:
            await client.chat_postMessage(
                channel=channel_id, thread_ts=thread_ts, text=USAGE_MESSAGE
            )
            return

        await analyze_targets(
            client=client,
            rd_client=deps.rd_client,
            api_key=api_key,
            channel_id=channel_id,
            thread_ts=thread_ts,
            media=media,
            url=url,
            bot_token=context["bot_token"],
        )

    except Exception:
        logger.exception("Error handling app_mention in channel %s", channel_id)
