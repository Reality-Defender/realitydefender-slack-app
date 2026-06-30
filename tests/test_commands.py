from collections.abc import Callable
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from slack_bolt.app.async_app import AsyncApp

from reality_defender_slack_app.deps import Deps
from reality_defender_slack_app.handlers import commands
from tests.helpers import HandlerRecorder, make_deps


def _handler(deps: Deps, name: str) -> Callable[..., Any]:
    rec = HandlerRecorder()
    commands.register_command_handlers(cast(AsyncApp, rec), deps)
    return rec.handlers[("command", name)]


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
