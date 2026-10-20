from typing import Any
from unittest.mock import AsyncMock

import pytest

from reality_defender_slack_app.handlers import mentions
from reality_defender_slack_app.services.keys import SETUP_REQUIRED_MESSAGE
from tests.helpers import make_deps

CONTEXT = {"team_id": "T1", "bot_token": "xoxb"}


@pytest.fixture
def analyze(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Stub the shared fan-out so tests assert what the mention extracts."""
    mock = AsyncMock()
    monkeypatch.setattr(mentions, "analyze_targets", mock)
    return mock


def _posted_texts(client: AsyncMock) -> list[str]:
    return [c.kwargs["text"] for c in client.chat_postMessage.call_args_list]


def _event(text: str = "<@BOT>", **extra: Any) -> dict[str, Any]:
    return {"channel": "C1", "ts": "1.1", "text": text, **extra}


@pytest.mark.asyncio
async def test_mention_without_key_prompts_setup(analyze: AsyncMock) -> None:
    client = AsyncMock()
    await mentions._process_mention(
        make_deps(shared_key=None), client, CONTEXT, _event("<@BOT> hi")
    )
    assert SETUP_REQUIRED_MESSAGE in _posted_texts(client)
    analyze.assert_not_awaited()


@pytest.mark.asyncio
async def test_mention_no_media_or_url_posts_usage(analyze: AsyncMock) -> None:
    client = AsyncMock()
    await mentions._process_mention(
        make_deps(shared_key="k"), client, CONTEXT, _event("<@BOT> hello there")
    )
    assert any("attach a file" in t for t in _posted_texts(client))
    analyze.assert_not_awaited()


@pytest.mark.asyncio
async def test_mention_ignores_non_social_url(analyze: AsyncMock) -> None:
    client = AsyncMock()
    await mentions._process_mention(
        make_deps(shared_key="k"),
        client,
        CONTEXT,
        _event("<@BOT> <https://example.com/video>"),
    )
    assert any("attach a file" in t for t in _posted_texts(client))
    analyze.assert_not_awaited()


@pytest.mark.asyncio
async def test_mention_with_social_url_calls_analyze_targets(analyze: AsyncMock) -> None:
    client = AsyncMock()
    await mentions._process_mention(
        make_deps(shared_key="k"),
        client,
        CONTEXT,
        _event("<@BOT> <https://x.com/a/status/1>"),
    )
    analyze.assert_awaited_once()
    assert analyze.call_args.kwargs["url"] == "https://x.com/a/status/1"
    assert analyze.call_args.kwargs["media"] == []
    assert analyze.call_args.kwargs["thread_ts"] == "1.1"


@pytest.mark.asyncio
async def test_mention_with_file_calls_analyze_targets(analyze: AsyncMock) -> None:
    client = AsyncMock()
    event = _event(
        files=[{"mimetype": "image/png", "url_private_download": "u1", "name": "a.png"}]
    )
    await mentions._process_mention(make_deps(shared_key="k"), client, CONTEXT, event)
    analyze.assert_awaited_once()
    assert analyze.call_args.kwargs["media"] == [("u1", "a.png")]
    assert analyze.call_args.kwargs["url"] is None


@pytest.mark.asyncio
async def test_mention_uses_existing_thread(analyze: AsyncMock) -> None:
    client = AsyncMock()
    await mentions._process_mention(
        make_deps(shared_key="k"),
        client,
        CONTEXT,
        _event("<@BOT> <https://x.com/a/status/1>", thread_ts="99.9"),
    )
    analyze.assert_awaited_once()
    assert analyze.call_args.kwargs["thread_ts"] == "99.9"
