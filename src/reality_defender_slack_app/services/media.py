from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

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

# The bot token is only ever sent to Slack's private file host. Redirects are
# followed only within Slack's own domains, without the token.
SLACK_FILE_HOST = "files.slack.com"
SLACK_CDN_DOMAINS = ("slack.com", "slack-edge.com", "slack-files.com")
MAX_REDIRECTS = 3

# Share-tracking parameters added by social apps; they don't identify the post.
_TRACKING_PARAMS = ("igsh", "stkn", "si", "fbclid", "gclid", "mibextid")

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


def clean_social_url(url: str) -> str:
    """Undo Slack's HTML escaping and drop share-tracking query parameters.

    Slack sends `&` as `&amp;` in message text; passed through as-is it corrupts
    every link with more than one parameter (e.g. YouTube `watch?v=...&t=...`).
    Parameters that identify the content (like YouTube's `v`) are kept.
    """
    parsed = urlparse(html.unescape(url))
    kept = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS
    ]
    return urlunparse(parsed._replace(query=urlencode(kept)))


def extract_social_url(text: str) -> str | None:
    """Return the first supported social media URL in Slack-formatted text."""
    for raw in _SLACK_LINK_RE.findall(text):
        url = clean_social_url(str(raw))
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
            if url and is_slack_file_url(url):
                media.append((url, file.get("name") or "media"))

    # Image blocks can point anywhere (another app or webhook sets image_url),
    # so only Slack-hosted images are collected; the bot token is only ever
    # sent to Slack's file host.
    for block in message.get("blocks", []):
        if block.get("type") == "image":
            for url in (block.get("slack_file", {}).get("url"), block.get("image_url")):
                if url and is_slack_file_url(url):
                    media.append((url, "image"))
                    break

    return media


def _host(url: str) -> str:
    parsed = urlparse(url)
    return (parsed.hostname or "").lower() if parsed.scheme == "https" else ""


def is_slack_file_url(url: str) -> bool:
    """True for Slack private file URLs (the only place the bot token may go)."""
    return _host(url) == SLACK_FILE_HOST


def _is_slack_cdn_url(url: str) -> bool:
    host = _host(url)
    return any(host == h or host.endswith("." + h) for h in SLACK_CDN_DOMAINS)


async def download_slack_file(url: str, bot_token: str) -> bytes:
    """Download a Slack private file using the workspace's bot token.

    Refuses anything but Slack's file host, follows redirects by hand so the
    token is never carried to another host, and only follows redirects that
    stay on Slack's own domains.
    """
    if not is_slack_file_url(url):
        raise ValueError(f"Refusing to download a non-Slack file URL: {_host(url) or url}")

    timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for _ in range(MAX_REDIRECTS + 1):
            headers = {"Authorization": f"Bearer {bot_token}"} if is_slack_file_url(url) else {}
            async with session.get(url, headers=headers, allow_redirects=False) as resp:
                if resp.status in (301, 302, 303, 307, 308):
                    location = urljoin(url, resp.headers.get("Location", ""))
                    if not _is_slack_cdn_url(location):
                        raise ValueError(
                            f"Refusing redirect off Slack's domains: {_host(location) or location}"
                        )
                    url = location
                    continue
                resp.raise_for_status()
                return await resp.read()
    raise ValueError("Too many redirects downloading Slack file")
