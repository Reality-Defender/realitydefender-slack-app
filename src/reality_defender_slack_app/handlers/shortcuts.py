from __future__ import annotations

import logging
from typing import Any

from slack_bolt.app.async_app import AsyncApp

from reality_defender_slack_app.background import spawn
from reality_defender_slack_app.deps import Deps
from reality_defender_slack_app.services.analysis import analyze_file_and_post
from reality_defender_slack_app.services.keys import resolve_api_key
from reality_defender_slack_app.services.media import (
    SUPPORTED_MIMETYPES,
    download_slack_file,
)
from reality_defender_slack_app.views import (
    notify_acknowledge_analysis_request,
    notify_error_user_unavailable,
)

logger = logging.getLogger(__name__)


def _collect_media(message: dict) -> list[tuple[str, str]]:
    """Return (url, filename) pairs for supported media in a message."""
    media: list[tuple[str, str]] = []

    for file in message.get("files", []):
        if file.get("mimetype", "") in SUPPORTED_MIMETYPES:
            url = file.get("url_private_download") or file.get("url_private")
            if url:
                media.append((url, file.get("name") or "media"))

    for block in message.get("blocks", []):
        if block.get("type") == "image":
            url = block.get("image_url") or block.get("slack_file", {}).get("url")
            if url:
                media.append((url, "image"))

    return media


def register_shortcut_handlers(app: AsyncApp, deps: Deps) -> None:
    @app.shortcut("analyze")
    async def handle_analyze(ack: Any, shortcut: Any, client: Any, context: Any) -> None:
        await ack()

        team_id = context.get("team_id")
        user_id = shortcut.get("user", {}).get("id", "")
        channel_id = shortcut.get("channel", {}).get("id", "")
        message_ts = shortcut.get("message_ts", "")
        trigger_id = shortcut.get("trigger_id", "")

        api_key = await resolve_api_key(deps.key_store, team_id, deps.settings)
        if not api_key:
            await notify_error_user_unavailable(client, trigger_id)
            return

        media = _collect_media(shortcut.get("message", {}))
        if not media:
            await notify_acknowledge_analysis_request(client, trigger_id, unsupported=True)
            return

        await notify_acknowledge_analysis_request(client, trigger_id)

        bot_token = context["bot_token"]
        for url, name in media:
            spawn(
                _download_and_analyze(
                    deps,
                    client,
                    api_key=api_key,
                    team_id=team_id or "",
                    user_id=user_id,
                    channel_id=channel_id,
                    thread_ts=message_ts,
                    url=url,
                    name=name,
                    bot_token=bot_token,
                )
            )


async def _download_and_analyze(
    deps: Deps,
    client: Any,
    *,
    api_key: str,
    team_id: str,
    user_id: str,
    channel_id: str,
    thread_ts: str,
    url: str,
    name: str,
    bot_token: str,
) -> None:
    try:
        content = await download_slack_file(url, bot_token)
    except Exception:
        logger.exception("Failed to download shortcut media %s", url)
        return

    await analyze_file_and_post(
        client=client,
        rd_client=deps.rd_client,
        tracker=deps.tracker,
        api_key=api_key,
        team_id=team_id,
        user_id=user_id,
        channel_id=channel_id,
        thread_ts=thread_ts,
        content=content,
        filename=name,
    )
