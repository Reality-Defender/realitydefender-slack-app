from __future__ import annotations

import logging
from typing import Any

from realitydefender.errors import RealityDefenderError

from reality_defender_slack_app.background import spawn
from reality_defender_slack_app.services.formatting import format_result
from reality_defender_slack_app.services.media import download_slack_file
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
) -> None:
    """Download a Slack file, post an analyzing ack, then analyze and post results."""
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

    try:
        result, media_id = await rd_client.analyze_file_bytes(api_key, content, name)
        reply = format_result(result, name, media_id=media_id)
    except RealityDefenderError as e:
        logger.error("RD error on file %s: %s (%s)", name, e.message, e.code)
        reply = f":x: Analysis failed: {e.message}"
    except Exception:
        logger.exception("Error processing file %s", name)
        reply = ":x: Something went wrong while processing your file."

    await client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=reply)


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
            )
        )
