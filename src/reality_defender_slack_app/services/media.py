from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import aiohttp

SOCIAL_MEDIA_DOMAINS = {
    "youtube.com",
    "youtu.be",
    "twitter.com",
    "x.com",
    "instagram.com",
    "facebook.com",
    "fb.com",
    "tiktok.com",
}

# Slack renders links as <https://url> or <https://url|label>; grab the URL part.
_SLACK_LINK_RE = re.compile(r"<(https?://[^>|]+)")

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

# Friendlier file extensions for the supported MIME types, for user-facing help.
# Types without an entry fall back to the MIME subtype (e.g. "image/heic" -> "heic").
_MIMETYPE_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "video/mp4": "mp4",
    "video/mov": "mov",
    "audio/mpeg": "mp3",
    "audio/flac": "flac",
    "audio/wav": "wav",
    "audio/mp4": "m4a",
    "audio/aac": "aac",
    "audio/ogg": "ogg",
}

# Slack file downloads can be large; cap how long we wait on the transfer.
DOWNLOAD_TIMEOUT_SECONDS = 60


def supported_extensions() -> list[str]:
    """Sorted, de-duplicated friendly file extensions for the supported types."""
    return sorted(
        {_MIMETYPE_EXTENSIONS.get(m, m.split("/")[-1]) for m in SUPPORTED_MIMETYPES}
    )


def is_social_url(url: str) -> bool:
    """True if the URL points at a supported social media domain."""
    domain = urlparse(url).netloc.lower().removeprefix("www.")
    return any(domain == d or domain.endswith("." + d) for d in SOCIAL_MEDIA_DOMAINS)


def extract_social_url(text: str) -> str | None:
    """Return the first supported social media URL in Slack-formatted text."""
    for raw in _SLACK_LINK_RE.findall(text):
        url = str(raw)
        if is_social_url(url):
            return url
    return None


def collect_media(message: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (url, filename) pairs for supported media in a message payload.

    Works for any message-shaped dict — a shortcut's `message` or an
    `app_mention` event both carry `files` and `blocks`.
    """
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


async def download_slack_file(url: str, bot_token: str) -> bytes:
    """Download a Slack private file using the workspace's bot token."""
    timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT_SECONDS)
    headers = {"Authorization": f"Bearer {bot_token}"}
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            return await resp.read()
