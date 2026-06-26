from collections.abc import Callable
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from slack_bolt.app.async_app import AsyncApp

from reality_defender_slack_app.deps import Deps
from reality_defender_slack_app.handlers import commands
from reality_defender_slack_app.services.keys import SETUP_REQUIRED_MESSAGE
from tests.helpers import HandlerRecorder, make_deps


@pytest.fixture(autouse=True)
def spawned(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Neutralize background spawning and record spawned coroutines."""
    captured: list[Any] = []

    def fake_spawn(coro: Any) -> None:
        captured.append(coro)
        coro.close()  # avoid "coroutine was never awaited" warnings

    monkeypatch.setattr(commands, "spawn", fake_spawn)
    return captured


def _handler(deps: Deps, name: str) -> Callable[..., Any]:
    rec = HandlerRecorder()
    commands.register_command_handlers(cast(AsyncApp, rec), deps)
    return rec.handlers[("command", name)]


# --- /detect ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_empty_url_prompts_usage() -> None:
    handler = _handler(make_deps(shared_key="k"), "/detect")
    respond, client = AsyncMock(), AsyncMock()

    await handler(
        ack=AsyncMock(),
        command={"text": "  ", "channel_id": "C1"},
        client=client,
        context={"team_id": "T1"},
        respond=respond,
    )

    assert "provide a URL" in respond.call_args.args[0]
    client.chat_postMessage.assert_not_called()


@pytest.mark.asyncio
async def test_detect_non_social_url_rejected() -> None:
    handler = _handler(make_deps(shared_key="k"), "/detect")
    respond, client = AsyncMock(), AsyncMock()

    await handler(
        ack=AsyncMock(),
        command={"text": "https://example.com/video", "channel_id": "C1"},
        client=client,
        context={"team_id": "T1"},
        respond=respond,
    )

    assert "Unsupported social media link" in respond.call_args.args[0]
    client.chat_postMessage.assert_not_called()


@pytest.mark.asyncio
async def test_detect_without_key_prompts_setup() -> None:
    # No shared key and an empty key store -> resolve returns None.
    handler = _handler(make_deps(shared_key=None), "/detect")
    respond, client = AsyncMock(), AsyncMock()

    await handler(
        ack=AsyncMock(),
        command={"text": "https://x.com/a/status/1", "channel_id": "C1"},
        client=client,
        context={"team_id": "T1"},
        respond=respond,
    )

    assert respond.call_args.args[0] == SETUP_REQUIRED_MESSAGE
    client.chat_postMessage.assert_not_called()


@pytest.mark.asyncio
async def test_detect_happy_path_posts_and_spawns(spawned: list[Any]) -> None:
    handler = _handler(make_deps(shared_key="k"), "/detect")
    client = AsyncMock()
    client.chat_postMessage = AsyncMock(return_value={"ts": "111.22"})

    await handler(
        ack=AsyncMock(),
        command={"text": "https://x.com/a/status/1", "channel_id": "C1"},
        client=client,
        context={"team_id": "T1"},
        respond=AsyncMock(),
    )

    client.chat_postMessage.assert_awaited_once()
    assert "Analyzing" in client.chat_postMessage.call_args.kwargs["text"]
    assert len(spawned) == 1


# --- /setup-rd -------------------------------------------------------------


@pytest.mark.asyncio
async def test_setup_rd_empty_key_prompts_usage() -> None:
    deps = make_deps()
    handler = _handler(deps, "/setup-rd")
    respond = AsyncMock()

    await handler(
        ack=AsyncMock(),
        command={"text": ""},
        context={"team_id": "T1"},
        respond=respond,
    )

    assert "Usage:" in respond.call_args.args[0]
    assert await deps.key_store.get("T1") is None


@pytest.mark.asyncio
async def test_setup_rd_without_team_errors() -> None:
    handler = _handler(make_deps(), "/setup-rd")
    respond = AsyncMock()

    await handler(
        ack=AsyncMock(),
        command={"text": "rd-key"},
        context={},
        respond=respond,
    )

    assert "workspace" in respond.call_args.args[0].lower()


@pytest.mark.asyncio
async def test_setup_rd_saves_workspace_key() -> None:
    deps = make_deps()
    handler = _handler(deps, "/setup-rd")
    respond = AsyncMock()

    await handler(
        ack=AsyncMock(),
        command={"text": "rd-key-xyz"},
        context={"team_id": "T9"},
        respond=respond,
    )

    assert await deps.key_store.get("T9") == "rd-key-xyz"
    assert "saved" in respond.call_args.args[0].lower()
