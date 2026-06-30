from __future__ import annotations

import logging
from typing import Any

from slack_bolt.app.async_app import AsyncApp

from reality_defender_slack_app.deps import Deps
from reality_defender_slack_app.services.analysis import analyze_targets
from reality_defender_slack_app.services.keys import resolve_api_key
from reality_defender_slack_app.services.media import collect_media, extract_social_url
from reality_defender_slack_app.views import (
    notify_acknowledge_analysis_request,
    notify_error_user_unavailable,
)

logger = logging.getLogger(__name__)


def register_shortcut_handlers(app: AsyncApp, deps: Deps) -> None:
    @app.shortcut("analyze")
    async def handle_analyze(ack: Any, shortcut: Any, client: Any, context: Any) -> None:
        await ack()

        team_id = context.get("team_id")
        channel_id = shortcut.get("channel", {}).get("id", "")
        message_ts = shortcut.get("message_ts", "")
        trigger_id = shortcut.get("trigger_id", "")

        api_key = await resolve_api_key(deps.key_store, team_id, deps.settings)
        if not api_key:
            await notify_error_user_unavailable(client, trigger_id)
            return

        message = shortcut.get("message", {})
        media = collect_media(message)
        url = extract_social_url(message.get("text", ""))

        if not media and not url:
            await notify_acknowledge_analysis_request(client, trigger_id, unsupported=True)
            return

        # Immediate modal feedback; the hourglass acks and results post to the thread.
        await notify_acknowledge_analysis_request(client, trigger_id)
        await analyze_targets(
            client=client,
            rd_client=deps.rd_client,
            api_key=api_key,
            channel_id=channel_id,
            thread_ts=message_ts,
            media=media,
            url=url,
            bot_token=context["bot_token"],
        )
