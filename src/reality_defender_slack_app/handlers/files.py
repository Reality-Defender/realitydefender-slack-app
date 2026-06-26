from __future__ import annotations

import logging
from typing import Any

from slack_bolt.app.async_app import AsyncApp

from reality_defender_slack_app.background import spawn
from reality_defender_slack_app.deps import Deps
from reality_defender_slack_app.services.analysis import analyze_file_and_post
from reality_defender_slack_app.services.keys import (
    SETUP_REQUIRED_MESSAGE,
    resolve_api_key,
)
from reality_defender_slack_app.services.media import (
    SUPPORTED_MIMETYPES,
    download_slack_file,
)

logger = logging.getLogger(__name__)


def register_file_handlers(app: AsyncApp, deps: Deps) -> None:
    @app.event("file_shared")
    async def handle_file_shared(event: Any, client: Any, context: Any, ack: Any) -> None:
        await ack()
        spawn(
            _process_file(
                deps,
                client,
                context,
                file_id=event.get("file_id"),
                channel_id=event.get("channel_id"),
                user_id=event.get("user_id", ""),
            )
        )


async def _process_file(
    deps: Deps,
    client: Any,
    context: Any,
    *,
    file_id: str,
    channel_id: str,
    user_id: str,
) -> None:
    try:
        file_info = await client.files_info(file=file_id)
        file = file_info["file"]
        filename = file["name"]
        mimetype = file.get("mimetype", "")

        # files.info returns the exact ts of the message the file was shared in,
        # under shares.public or shares.private keyed by channel_id.
        shares = file.get("shares", {})
        channel_shares = (
            shares.get("public", {}).get(channel_id)
            or shares.get("private", {}).get(channel_id)
            or []
        )
        thread_ts = channel_shares[0]["ts"] if channel_shares else ""

        if mimetype not in SUPPORTED_MIMETYPES:
            supported = ", ".join(f"`{m}`" for m in sorted(SUPPORTED_MIMETYPES))
            await client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=f"Unsupported file type `{mimetype}`. Supported: {supported}",
            )
            return

        team_id = context.get("team_id")
        api_key = await resolve_api_key(deps.key_store, team_id, deps.settings)
        if not api_key:
            await client.chat_postMessage(
                channel=channel_id, thread_ts=thread_ts, text=SETUP_REQUIRED_MESSAGE
            )
            return

        url = file.get("url_private_download") or file.get("url_private")
        content = await download_slack_file(url, context["bot_token"])

        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f":hourglass_flowing_sand: Analyzing `{filename}`...",
        )

        await analyze_file_and_post(
            client=client,
            rd_client=deps.rd_client,
            tracker=deps.tracker,
            api_key=api_key,
            team_id=team_id or "",
            user_id=user_id,
            channel_id=channel_id,
            thread_ts=thread_ts,
            content=content,
            filename=filename,
        )
    except Exception:
        logger.exception("Error processing file %s", file_id)
