from __future__ import annotations

import contextlib
import logging
import re
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, NamedTuple

from realitydefender import RealityDefender
from realitydefender.detection.results import get_media_result
from realitydefender.model import DetectionResult, FeedbackLabel, UserFeedbackCategory

logger = logging.getLogger(__name__)

# get_result polls internally, returning as soon as the status leaves ANALYZING
# (or the current result once max attempts is hit). 150 attempts at 2s ~= 5 min.
POLLING_INTERVAL_MS = 2000
MAX_POLL_ATTEMPTS = 150


class Analysis(NamedTuple):
    """Outcome of one scan.

    `result` is the SDK's trimmed DetectionResult (status, score, models). `raw`
    is the full media record (per-model data, file metadata, signed evidence
    URLs) used to build the PDF report; None if that follow-up fetch failed.
    """

    result: DetectionResult
    request_id: str
    media_id: str | None
    raw: dict[str, Any] | None


@contextlib.asynccontextmanager
async def _rd_session(api_key: str) -> AsyncIterator[RealityDefender]:
    """Yield a RealityDefender client for the given key, cleaning up afterward."""
    logger.info("Opening Reality Defender session")
    rd = RealityDefender(api_key=api_key)
    try:
        yield rd
    finally:
        try:
            await rd.cleanup()
            logger.info("Closed Reality Defender session")
        except Exception:
            logger.warning("Reality Defender session cleanup failed", exc_info=True)


async def _fetch_raw(rd: RealityDefender, request_id: str) -> dict[str, Any] | None:
    """Fetch the full media record once polling has finished.

    get_result() already waited for a verdict, so this is a single request. A
    failure here only costs the report, never the result.
    """
    try:
        raw = await get_media_result(rd.client, request_id)
    except Exception:
        logger.warning("Could not fetch full result for %s", request_id, exc_info=True)
        return None
    return raw if isinstance(raw, dict) else None


def _safe_filename(filename: str) -> str:
    """Keep the user's filename (RD records it) but make it filesystem-safe."""
    name = re.sub(r"[^\w.\- ]+", "_", Path(filename).name).strip(" .")
    return name[:120] or "media"


class RDClient:
    """Wraps the Reality Defender SDK. The API key is passed per call so a single
    instance can serve many workspaces, each with its own key."""

    async def analyze_url(self, api_key: str, url: str) -> Analysis:
        """media_id is None for social media submissions."""
        async with _rd_session(api_key) as rd:
            logger.info("Submitting social media URL: %s", url)
            upload = await rd.upload_social_media(social_media_link=url)
            result = await rd.get_result(
                upload["request_id"],
                max_attempts=MAX_POLL_ATTEMPTS,
                polling_interval=POLLING_INTERVAL_MS,
            )
            raw = await _fetch_raw(rd, upload["request_id"])
            return Analysis(result, upload["request_id"], upload.get("media_id"), raw)

    async def analyze_file_bytes(
        self, api_key: str, file_bytes: bytes, filename: str
    ) -> Analysis:
        # Upload under the original name (in a private temp dir) so RD's record,
        # dashboard and report show the real filename, not a random temp name.
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / _safe_filename(filename)
            if not tmp_path.suffix:
                tmp_path = tmp_path.with_suffix(".bin")
            tmp_path.write_bytes(file_bytes)
            logger.info("Submitting file: %s (%d bytes)", filename, len(file_bytes))
            async with _rd_session(api_key) as rd:
                # Two-step instead of detect_file() so we can capture media_id
                upload = await rd.upload(file_path=str(tmp_path))
                result = await rd.get_result(
                    upload["request_id"],
                    max_attempts=MAX_POLL_ATTEMPTS,
                    polling_interval=POLLING_INTERVAL_MS,
                )
                raw = await _fetch_raw(rd, upload["request_id"])
                return Analysis(result, upload["request_id"], upload.get("media_id"), raw)

    async def submit_feedback(
        self,
        api_key: str,
        request_id: str,
        *,
        label: FeedbackLabel,
        category: UserFeedbackCategory,
        comment: str | None = None,
    ) -> None:
        """Report a false positive/negative, a confirmation, or a question on a scan."""
        async with _rd_session(api_key) as rd:
            logger.info("Submitting %s feedback for %s", category, request_id)
            await rd.create_user_feedback(request_id, label, category, comment=comment)
