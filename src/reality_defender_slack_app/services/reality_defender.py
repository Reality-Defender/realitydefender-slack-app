from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

from realitydefender import RealityDefender
from realitydefender.model import DetectionResult

logger = logging.getLogger(__name__)

# get_result polls internally, returning as soon as the status leaves ANALYZING
# (or the current result once max attempts is hit). 150 attempts at 2s ~= 5 min.
POLLING_INTERVAL_MS = 2000
MAX_POLL_ATTEMPTS = 150


@contextlib.asynccontextmanager
async def _rd_session(api_key: str) -> AsyncIterator[RealityDefender]:
    """Yield a RealityDefender client for the given key, cleaning up afterward."""
    rd = RealityDefender(api_key=api_key)
    try:
        yield rd
    finally:
        with contextlib.suppress(Exception):
            await rd.cleanup()


class RDClient:
    """Wraps the Reality Defender SDK. The API key is passed per call so a single
    instance can serve many workspaces, each with its own key."""

    async def analyze_url(self, api_key: str, url: str) -> tuple[DetectionResult, str | None]:
        """Returns (result, media_id). media_id is None for social media submissions."""
        async with _rd_session(api_key) as rd:
            logger.info("Submitting social media URL: %s", url)
            upload = await rd.upload_social_media(social_media_link=url)
            result = await rd.get_result(
                upload["request_id"],
                max_attempts=MAX_POLL_ATTEMPTS,
                polling_interval=POLLING_INTERVAL_MS,
            )
            return result, upload.get("media_id")

    async def analyze_file_bytes(
        self, api_key: str, file_bytes: bytes, filename: str
    ) -> tuple[DetectionResult, str | None]:
        """Returns (result, media_id)."""
        suffix = Path(filename).suffix or ".bin"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(file_bytes)
            tmp_path = f.name
        try:
            logger.info("Submitting file: %s (%d bytes)", filename, len(file_bytes))
            async with _rd_session(api_key) as rd:
                # Two-step instead of detect_file() so we can capture media_id
                upload = await rd.upload(file_path=tmp_path)
                result = await rd.get_result(
                    upload["request_id"],
                    max_attempts=MAX_POLL_ATTEMPTS,
                    polling_interval=POLLING_INTERVAL_MS,
                )
                return result, upload.get("media_id")
        finally:
            os.unlink(tmp_path)
