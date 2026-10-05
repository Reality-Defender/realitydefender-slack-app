from __future__ import annotations

import hashlib
import logging
from collections.abc import Awaitable
from datetime import datetime, timezone
from typing import Any

from realitydefender.errors import RealityDefenderError

from reality_defender_slack_app.background import spawn
from reality_defender_slack_app.services.formatting import format_result, result_blocks
from reality_defender_slack_app.services.media import download_slack_file
from reality_defender_slack_app.services.reality_defender import Analysis, RDClient
from reality_defender_slack_app.services.report import ScanContext, render_report

logger = logging.getLogger(__name__)


async def analyze_url_and_post(
    *,
    client: Any,
    rd_client: RDClient,
    api_key: str,
    channel_id: str,
    thread_ts: str,
    url: str,
    requester_id: str | None = None,
    message_ts: str | None = None,
) -> None:
    """Analyze a social media URL and post the result into the message thread."""
    context = ScanContext("social", url, datetime.now(timezone.utc))
    analysis = None
    try:
        analysis = await rd_client.analyze_url(api_key, url)
        reply = format_result(analysis.result, url, media_id=analysis.media_id)
    except RealityDefenderError as e:
        logger.error("RD API error analyzing %s: %s (%s)", url, e.message, e.code)
        reply = f":x: Analysis failed: {e.message} (`{e.code}`)"
    except Exception:
        logger.exception("Unexpected error analyzing URL %s", url)
        reply = ":x: Something went wrong. Please try again."

    await _post_result(
        client=client,
        channel_id=channel_id,
        thread_ts=thread_ts,
        reply=reply,
        analysis=analysis,
        context=context,
        requester_id=requester_id,
        message_ts=message_ts,
    )


async def analyze_slack_file_and_post(
    *,
    client: Any,
    rd_client: RDClient,
    api_key: str,
    channel_id: str,
    thread_ts: str,
    file_url: str,
    name: str,
    bot_token: str,
    requester_id: str | None = None,
    message_ts: str | None = None,
) -> None:
    """Download a Slack file, post an analyzing ack, then analyze and post results."""
    requested_at = datetime.now(timezone.utc)
    try:
        content = await download_slack_file(file_url, bot_token)
    except Exception:
        logger.exception("Failed to download Slack file %s", file_url)
        return

    await client.chat_postMessage(
        channel=channel_id,
        thread_ts=thread_ts,
        text=f":hourglass_flowing_sand: Analyzing `{name}`...",
    )

    # Hash of the exact bytes scanned, so the verdict can be tied to this file
    # even after it's re-shared or renamed.
    context = ScanContext(
        "upload", name, requested_at, sha256=hashlib.sha256(content).hexdigest()
    )
    analysis = None
    try:
        analysis = await rd_client.analyze_file_bytes(api_key, content, name)
        reply = format_result(analysis.result, name, media_id=analysis.media_id)
    except RealityDefenderError as e:
        logger.error("RD error on file %s: %s (%s)", name, e.message, e.code)
        reply = f":x: Analysis failed: {e.message}"
    except Exception:
        logger.exception("Error processing file %s", name)
        reply = ":x: Something went wrong while processing your file."

    await _post_result(
        client=client,
        channel_id=channel_id,
        thread_ts=thread_ts,
        reply=reply,
        analysis=analysis,
        context=context,
        requester_id=requester_id,
        message_ts=message_ts,
        media_bytes=content,
    )


async def _post_result(
    *,
    client: Any,
    channel_id: str,
    thread_ts: str,
    reply: str,
    analysis: Analysis | None,
    context: ScanContext,
    requester_id: str | None,
    message_ts: str | None,
    media_bytes: bytes | None = None,
) -> None:
    """Post the result with its "Report an issue" button, then the PDF report.

    The PDF is a follow-up upload in the same thread; if it can't be built the
    result message stands on its own.
    """
    if analysis is None:
        await client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=reply)
        return

    await client.chat_postMessage(
        channel=channel_id,
        thread_ts=thread_ts,
        text=reply,
        blocks=result_blocks(reply, analysis.request_id, analysis.result["status"]),
    )
    if analysis.raw is None:
        return

    try:
        # Who/where for the report cover; each lookup is optional.
        auth = await _lookup(client.auth_test())
        context.workspace_name = auth.get("team") if auth else None
        if requester_id:
            user = await _lookup(client.users_info(user=requester_id))
            profile = user["user"]["profile"] if user else {}
            context.requested_by = profile.get("real_name") or profile.get("display_name")
        if message_ts:
            link = await _lookup(
                client.chat_getPermalink(channel=channel_id, message_ts=message_ts)
            )
            context.message_permalink = link.get("permalink") if link else None

        pdf, filename = await render_report(
            analysis.raw, context, media_id=analysis.media_id, media_bytes=media_bytes
        )
        await client.files_upload_v2(
            channel=channel_id,
            thread_ts=thread_ts,
            file=pdf,
            filename=filename,
            title="Reality Defender report",
        )
    except Exception:
        logger.exception("Failed to build or upload report for %s", analysis.request_id)


async def _lookup(call: Awaitable[Any]) -> Any:
    """Await a Slack API call, returning None if it fails."""
    try:
        return await call
    except Exception:
        logger.debug("Slack lookup failed", exc_info=True)
        return None


async def analyze_targets(
    *,
    client: Any,
    rd_client: RDClient,
    api_key: str,
    channel_id: str,
    thread_ts: str,
    media: list[tuple[str, str]],
    url: str | None,
    bot_token: str,
    requester_id: str | None = None,
    message_ts: str | None = None,
) -> None:
    """Fan out analysis for the media and/or social URL found at an entrypoint.

    Shared by every Slack entrypoint (mention, message shortcut): each file
    is downloaded and analyzed in the background and the URL, if any, is analyzed
    in the background. An hourglass ack is posted per target into the thread.
    """
    for file_url, name in media:
        spawn(
            analyze_slack_file_and_post(
                client=client,
                rd_client=rd_client,
                api_key=api_key,
                channel_id=channel_id,
                thread_ts=thread_ts,
                file_url=file_url,
                name=name,
                bot_token=bot_token,
                requester_id=requester_id,
                message_ts=message_ts,
            )
        )

    if url:
        await client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f":hourglass_flowing_sand: Analyzing `{url}`...",
        )
        spawn(
            analyze_url_and_post(
                client=client,
                rd_client=rd_client,
                api_key=api_key,
                channel_id=channel_id,
                thread_ts=thread_ts,
                url=url,
                requester_id=requester_id,
                message_ts=message_ts,
            )
        )
