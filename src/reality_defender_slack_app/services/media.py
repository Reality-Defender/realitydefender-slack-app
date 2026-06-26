from __future__ import annotations

import aiohttp

SUPPORTED_MIMETYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "image/gif",
    "video/mp4",
    "video/mov",
    "audio/mpeg",
    "audio/flac",
    "audio/wav",
    "audio/mp4",
    "audio/aac",
    "audio/ogg",
}

# Slack file downloads can be large; cap how long we wait on the transfer.
DOWNLOAD_TIMEOUT_SECONDS = 60


async def download_slack_file(url: str, bot_token: str) -> bytes:
    """Download a Slack private file using the workspace's bot token."""
    timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT_SECONDS)
    headers = {"Authorization": f"Bearer {bot_token}"}
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            return await resp.read()
