from __future__ import annotations

import logging
from typing import Any

from realitydefender.errors import RealityDefenderError

from reality_defender_slack_app.services.formatting import format_result
from reality_defender_slack_app.services.reality_defender import RDClient

logger = logging.getLogger(__name__)


async def analyze_url_and_post(
    *,
    client: Any,
    rd_client: RDClient,
    api_key: str,
    channel_id: str,
    thread_ts: str,
    url: str,
) -> None:
    """Analyze a social media URL and post the result into the message thread."""
    try:
        result, media_id = await rd_client.analyze_url(api_key, url)
        reply = format_result(result, url, media_id=media_id)
    except RealityDefenderError as e:
        logger.error("RD API error analyzing %s: %s (%s)", url, e.message, e.code)
        reply = f":x: Analysis failed: {e.message} (`{e.code}`)"
    except Exception:
        logger.exception("Unexpected error analyzing URL %s", url)
        reply = ":x: Something went wrong. Please try again."

    await client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=reply)


async def analyze_file_and_post(
    *,
    client: Any,
    rd_client: RDClient,
    api_key: str,
    channel_id: str,
    thread_ts: str,
    content: bytes,
    filename: str,
) -> None:
    """Analyze file bytes and post the result into the message thread."""
    try:
        result, media_id = await rd_client.analyze_file_bytes(api_key, content, filename)
        reply = format_result(result, filename, media_id=media_id)
    except RealityDefenderError as e:
        logger.error("RD error on file %s: %s (%s)", filename, e.message, e.code)
        reply = f":x: Analysis failed: {e.message}"
    except Exception:
        logger.exception("Error processing file %s", filename)
        reply = ":x: Something went wrong while processing your file."

    await client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=reply)
