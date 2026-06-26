from __future__ import annotations

import logging
from typing import Any

from realitydefender.errors import RealityDefenderError

from reality_defender_slack_app.services.formatting import format_result
from reality_defender_slack_app.services.reality_defender import RDClient
from reality_defender_slack_app.services.tracker import (
    STATUS_DONE,
    STATUS_FAILED,
    AnalysisTracker,
)

logger = logging.getLogger(__name__)


async def analyze_url_and_post(
    *,
    client: Any,
    rd_client: RDClient,
    tracker: AnalysisTracker,
    api_key: str,
    team_id: str,
    user_id: str,
    channel_id: str,
    thread_ts: str,
    url: str,
) -> None:
    """Analyze a social media URL and post the result into the message thread."""
    record_id = tracker.start(team_id, user_id, url)
    try:
        result, media_id = await rd_client.analyze_url(api_key, url)
        reply = format_result(result, url, media_id=media_id)
        tracker.finish(record_id, STATUS_DONE)
    except RealityDefenderError as e:
        logger.error("RD API error analyzing %s: %s (%s)", url, e.message, e.code)
        reply = f":x: Analysis failed: {e.message} (`{e.code}`)"
        tracker.finish(record_id, STATUS_FAILED)
    except Exception:
        logger.exception("Unexpected error analyzing URL %s", url)
        reply = ":x: Something went wrong. Please try again."
        tracker.finish(record_id, STATUS_FAILED)

    await client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=reply)


async def analyze_file_and_post(
    *,
    client: Any,
    rd_client: RDClient,
    tracker: AnalysisTracker,
    api_key: str,
    team_id: str,
    user_id: str,
    channel_id: str,
    thread_ts: str,
    content: bytes,
    filename: str,
) -> None:
    """Analyze file bytes and post the result into the message thread."""
    record_id = tracker.start(team_id, user_id, filename)
    try:
        result, media_id = await rd_client.analyze_file_bytes(api_key, content, filename)
        reply = format_result(result, filename, media_id=media_id)
        tracker.finish(record_id, STATUS_DONE)
    except RealityDefenderError as e:
        logger.error("RD error on file %s: %s (%s)", filename, e.message, e.code)
        reply = f":x: Analysis failed: {e.message}"
        tracker.finish(record_id, STATUS_FAILED)
    except Exception:
        logger.exception("Error processing file %s", filename)
        reply = ":x: Something went wrong while processing your file."
        tracker.finish(record_id, STATUS_FAILED)

    await client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=reply)
