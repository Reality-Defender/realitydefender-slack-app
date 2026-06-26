from __future__ import annotations

import logging
from typing import Any

from slack_bolt.app.async_app import AsyncApp

from reality_defender_slack_app.background import spawn
from reality_defender_slack_app.deps import Deps
from reality_defender_slack_app.services.analysis import (
    analyze_file_and_post,
    analyze_url_and_post,
)
from reality_defender_slack_app.services.keys import (
    SETUP_REQUIRED_MESSAGE,
    resolve_api_key,
)
from reality_defender_slack_app.services.media import (
    collect_media,
    download_slack_file,
    extract_social_url,
)

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

        if media:
            bot_token = context["bot_token"]
            for media_url, name in media:
                spawn(
                    _download_and_analyze(
                        deps,
                        client,
                        api_key=api_key,
                        channel_id=channel_id,
                        thread_ts=thread_ts,
                        url=media_url,
                        name=name,
                        bot_token=bot_token,
                    )
                )
            return

        if url:
            await client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=f":hourglass_flowing_sand: Analyzing `{url}`...",
            )
            spawn(
                analyze_url_and_post(
                    client=client,
                    rd_client=deps.rd_client,
                    api_key=api_key,
                    channel_id=channel_id,
                    thread_ts=thread_ts,
                    url=url,
                )
            )
            return

        await client.chat_postMessage(
            channel=channel_id, thread_ts=thread_ts, text=USAGE_MESSAGE
        )
    except Exception:
        logger.exception("Error handling app_mention in channel %s", channel_id)


async def _download_and_analyze(
    deps: Deps,
    client: Any,
    *,
    api_key: str,
    channel_id: str,
    thread_ts: str,
    url: str,
    name: str,
    bot_token: str,
) -> None:
    try:
        content = await download_slack_file(url, bot_token)
    except Exception:
        logger.exception("Failed to download mention media %s", url)
        return

    await client.chat_postMessage(
        channel=channel_id,
        thread_ts=thread_ts,
        text=f":hourglass_flowing_sand: Analyzing `{name}`...",
    )
    await analyze_file_and_post(
        client=client,
        rd_client=deps.rd_client,
        api_key=api_key,
        channel_id=channel_id,
        thread_ts=thread_ts,
        content=content,
        filename=name,
    )
