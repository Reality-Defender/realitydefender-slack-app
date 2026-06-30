from typing import Any
from unittest.mock import AsyncMock

import pytest

from reality_defender_slack_app.services import analysis


@pytest.fixture
def spawned(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Capture coroutines handed to spawn so the test can await them."""
    captured: list[Any] = []
    monkeypatch.setattr(analysis, "spawn", lambda coro: captured.append(coro))
    return captured


async def _drain(spawned: list[Any]) -> None:
    for coro in spawned:
        await coro


def _posted_texts(client: AsyncMock) -> list[str]:
    return [c.kwargs["text"] for c in client.chat_postMessage.call_args_list]


@pytest.mark.asyncio
async def test_analyze_targets_url_posts_hourglass_and_spawns(
    monkeypatch: pytest.MonkeyPatch, spawned: list[Any]
) -> None:
    analyze_url = AsyncMock()
    monkeypatch.setattr(analysis, "analyze_url_and_post", analyze_url)
    client = AsyncMock()

    await analysis.analyze_targets(
        client=client,
        rd_client=AsyncMock(),
        api_key="k",
        channel_id="C1",
        thread_ts="1.1",
        media=[],
        url="https://x.com/a/status/1",
        bot_token="xoxb",
    )

    assert any("Analyzing" in t for t in _posted_texts(client))
    assert len(spawned) == 1
    await _drain(spawned)
    analyze_url.assert_awaited_once()
    assert analyze_url.call_args.kwargs["url"] == "https://x.com/a/status/1"


@pytest.mark.asyncio
async def test_analyze_targets_file_downloads_then_analyzes(
    monkeypatch: pytest.MonkeyPatch, spawned: list[Any]
) -> None:
    download = AsyncMock(return_value=b"\x89PNG")
    monkeypatch.setattr(analysis, "download_slack_file", download)
    monkeypatch.setattr(analysis, "format_result", lambda *a, **k: "RESULT")
    client = AsyncMock()
    rd_client = AsyncMock()
    rd_client.analyze_file_bytes = AsyncMock(return_value=("res", "media-1"))

    await analysis.analyze_targets(
        client=client,
        rd_client=rd_client,
        api_key="k",
        channel_id="C1",
        thread_ts="1.1",
        media=[("u1", "a.png")],
        url=None,
        bot_token="xoxb",
    )

    assert len(spawned) == 1  # analyze_slack_file_and_post
    await _drain(spawned)
    download.assert_awaited_once_with("u1", "xoxb")
    rd_client.analyze_file_bytes.assert_awaited_once_with("k", b"\x89PNG", "a.png")
    texts = _posted_texts(client)
    assert any("Analyzing `a.png`" in t for t in texts)  # hourglass ack
    assert "RESULT" in texts  # analysis result


@pytest.mark.asyncio
async def test_analyze_targets_failed_download_skips_analysis(
    monkeypatch: pytest.MonkeyPatch, spawned: list[Any]
) -> None:
    download = AsyncMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(analysis, "download_slack_file", download)
    client = AsyncMock()
    rd_client = AsyncMock()

    await analysis.analyze_targets(
        client=client,
        rd_client=rd_client,
        api_key="k",
        channel_id="C1",
        thread_ts="1.1",
        media=[("u1", "a.png")],
        url=None,
        bot_token="xoxb",
    )

    await _drain(spawned)
    download.assert_awaited_once()
    rd_client.analyze_file_bytes.assert_not_awaited()
    # A failed download is silent: no hourglass, no result posted.
    assert _posted_texts(client) == []
