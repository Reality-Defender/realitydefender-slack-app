from typing import Any
from unittest.mock import AsyncMock

import pytest

from reality_defender_slack_app.handlers import mentions
from reality_defender_slack_app.services.keys import SETUP_REQUIRED_MESSAGE
from tests.helpers import make_deps

CONTEXT = {"team_id": "T1", "bot_token": "xoxb"}


@pytest.fixture
def spawned(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Capture coroutines handed to spawn so the test can await them."""
    captured: list[Any] = []
    monkeypatch.setattr(mentions, "spawn", lambda coro: captured.append(coro))
    return captured


async def _drain(spawned: list[Any]) -> None:
    for coro in spawned:
        await coro


def _posted_texts(client: AsyncMock) -> list[str]:
    return [c.kwargs["text"] for c in client.chat_postMessage.call_args_list]


def _event(text: str = "<@BOT>", **extra: Any) -> dict[str, Any]:
    return {"channel": "C1", "ts": "1.1", "text": text, **extra}


@pytest.mark.asyncio
async def test_mention_without_key_prompts_setup(spawned: list[Any]) -> None:
    client = AsyncMock()
    await mentions._process_mention(
        make_deps(shared_key=None), client, CONTEXT, _event("<@BOT> hi")
    )
    assert SETUP_REQUIRED_MESSAGE in _posted_texts(client)
    assert spawned == []


@pytest.mark.asyncio
async def test_mention_no_media_or_url_posts_usage(spawned: list[Any]) -> None:
    client = AsyncMock()
    await mentions._process_mention(
        make_deps(shared_key="k"), client, CONTEXT, _event("<@BOT> hello there")
    )
    assert any("attach a file" in t for t in _posted_texts(client))
    assert spawned == []


@pytest.mark.asyncio
async def test_mention_ignores_non_social_url(spawned: list[Any]) -> None:
    client = AsyncMock()
    await mentions._process_mention(
        make_deps(shared_key="k"),
        client,
        CONTEXT,
        _event("<@BOT> <https://example.com/video>"),
    )
    assert any("attach a file" in t for t in _posted_texts(client))
    assert spawned == []


@pytest.mark.asyncio
async def test_mention_with_social_url_spawns_url_analysis(
    monkeypatch: pytest.MonkeyPatch, spawned: list[Any]
) -> None:
    analyze = AsyncMock()
    monkeypatch.setattr(mentions, "analyze_url_and_post", analyze)
    client = AsyncMock()

    await mentions._process_mention(
        make_deps(shared_key="k"),
        client,
        CONTEXT,
        _event("<@BOT> <https://x.com/a/status/1>"),
    )

    assert any("Analyzing" in t for t in _posted_texts(client))
    assert len(spawned) == 1
    await _drain(spawned)
    analyze.assert_awaited_once()
    assert analyze.call_args.kwargs["url"] == "https://x.com/a/status/1"
    assert analyze.call_args.kwargs["thread_ts"] == "1.1"


@pytest.mark.asyncio
async def test_mention_with_file_spawns_file_analysis(
    monkeypatch: pytest.MonkeyPatch, spawned: list[Any]
) -> None:
    download = AsyncMock(return_value=b"\x89PNG")
    analyze = AsyncMock()
    monkeypatch.setattr(mentions, "download_slack_file", download)
    monkeypatch.setattr(mentions, "analyze_file_and_post", analyze)
    client = AsyncMock()

    event = _event(
        files=[
            {"mimetype": "image/png", "url_private_download": "u1", "name": "a.png"}
        ]
    )
    await mentions._process_mention(make_deps(shared_key="k"), client, CONTEXT, event)

    assert len(spawned) == 1  # _download_and_analyze
    await _drain(spawned)
    download.assert_awaited_once()
    analyze.assert_awaited_once()
    assert analyze.call_args.kwargs["filename"] == "a.png"
    assert analyze.call_args.kwargs["content"] == b"\x89PNG"


@pytest.mark.asyncio
async def test_mention_uses_existing_thread(
    monkeypatch: pytest.MonkeyPatch, spawned: list[Any]
) -> None:
    analyze = AsyncMock()
    monkeypatch.setattr(mentions, "analyze_url_and_post", analyze)
    client = AsyncMock()

    await mentions._process_mention(
        make_deps(shared_key="k"),
        client,
        CONTEXT,
        _event("<@BOT> <https://x.com/a/status/1>", thread_ts="99.9"),
    )

    await _drain(spawned)
    assert analyze.call_args.kwargs["thread_ts"] == "99.9"
