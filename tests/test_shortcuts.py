from collections.abc import Callable
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from slack_bolt.app.async_app import AsyncApp

from reality_defender_slack_app.deps import Deps
from reality_defender_slack_app.handlers import shortcuts
from reality_defender_slack_app.services import media
from tests.helpers import HandlerRecorder, make_deps

CONTEXT = {"team_id": "T1", "bot_token": "xoxb"}


def _handler(deps: Deps) -> Callable[..., Any]:
    rec = HandlerRecorder()
    shortcuts.register_shortcut_handlers(cast(AsyncApp, rec), deps)
    return rec.handlers[("shortcut", "analyze")]


def test_collect_media_includes_supported_file() -> None:
    message = {
        "files": [
            {"mimetype": "image/png", "url_private_download": "u1", "name": "a.png"}
        ]
    }
    assert media.collect_media(message) == [("u1", "a.png")]


def test_collect_media_skips_unsupported_file() -> None:
    message = {"files": [{"mimetype": "application/zip", "url_private": "u", "name": "z"}]}
    assert media.collect_media(message) == []


def test_collect_media_includes_image_block() -> None:
    message = {"blocks": [{"type": "image", "image_url": "img1"}]}
    assert media.collect_media(message) == [("img1", "image")]


def test_collect_media_empty_message() -> None:
    assert media.collect_media({}) == []


@pytest.fixture
def analyze(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Stub the shared fan-out so tests assert what the shortcut extracts."""
    mock = AsyncMock()
    monkeypatch.setattr(shortcuts, "analyze_targets", mock)
    return mock


def _shortcut(message: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    return {
        "channel": {"id": "C1"},
        "message_ts": "1.1",
        "trigger_id": "tg",
        "message": message or {},
        **extra,
    }


@pytest.mark.asyncio
async def test_shortcut_without_key_notifies(
    analyze: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    notify = AsyncMock()
    monkeypatch.setattr(shortcuts, "notify_error_user_unavailable", notify)
    handler = _handler(make_deps(shared_key=None))
    client = AsyncMock()

    await handler(ack=AsyncMock(), shortcut=_shortcut(), client=client, context=CONTEXT)

    notify.assert_awaited_once()
    analyze.assert_not_awaited()


@pytest.mark.asyncio
async def test_shortcut_no_media_or_url_notifies_unsupported(
    analyze: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    notify = AsyncMock()
    monkeypatch.setattr(shortcuts, "notify_acknowledge_analysis_request", notify)
    handler = _handler(make_deps(shared_key="k"))
    client = AsyncMock()

    await handler(ack=AsyncMock(), shortcut=_shortcut(), client=client, context=CONTEXT)

    notify.assert_awaited_once()
    assert notify.call_args.kwargs.get("unsupported") is True
    analyze.assert_not_awaited()


@pytest.mark.asyncio
async def test_shortcut_with_file_calls_analyze_targets(
    analyze: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shortcuts, "notify_acknowledge_analysis_request", AsyncMock())
    handler = _handler(make_deps(shared_key="k"))
    client = AsyncMock()
    message = {
        "files": [{"mimetype": "image/png", "url_private_download": "u1", "name": "a.png"}]
    }

    await handler(
        ack=AsyncMock(), shortcut=_shortcut(message), client=client, context=CONTEXT
    )

    analyze.assert_awaited_once()
    assert analyze.call_args.kwargs["media"] == [("u1", "a.png")]
    assert analyze.call_args.kwargs["thread_ts"] == "1.1"


@pytest.mark.asyncio
async def test_shortcut_with_social_url_calls_analyze_targets(
    analyze: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shortcuts, "notify_acknowledge_analysis_request", AsyncMock())
    handler = _handler(make_deps(shared_key="k"))
    client = AsyncMock()
    message = {"text": "<https://x.com/a/status/1>"}

    await handler(
        ack=AsyncMock(), shortcut=_shortcut(message), client=client, context=CONTEXT
    )

    analyze.assert_awaited_once()
    assert analyze.call_args.kwargs["url"] == "https://x.com/a/status/1"
