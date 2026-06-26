from collections.abc import Callable
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from slack_bolt.app.async_app import AsyncApp

from reality_defender_slack_app.deps import Deps
from reality_defender_slack_app.handlers import lifecycle
from tests.helpers import HandlerRecorder, make_deps


def _handler(deps: Deps, event_name: str) -> Callable[..., Any]:
    rec = HandlerRecorder()
    lifecycle.register_lifecycle_handlers(cast(AsyncApp, rec), deps)
    return rec.handlers[("event", event_name)]


@pytest.mark.asyncio
async def test_app_uninstalled_deletes_installation_and_key() -> None:
    inst = AsyncMock()
    deps = make_deps(installation_store=inst)
    await deps.key_store.set("T1", "rd-key")
    handler = _handler(deps, "app_uninstalled")

    await handler(context={"team_id": "T1", "enterprise_id": None}, ack=AsyncMock())

    inst.async_delete_all.assert_awaited_once_with(enterprise_id=None, team_id="T1")
    assert await deps.key_store.get("T1") is None


@pytest.mark.asyncio
async def test_app_uninstalled_passes_enterprise_id() -> None:
    inst = AsyncMock()
    deps = make_deps(installation_store=inst)
    handler = _handler(deps, "app_uninstalled")

    await handler(context={"team_id": None, "enterprise_id": "E1"}, ack=AsyncMock())

    inst.async_delete_all.assert_awaited_once_with(enterprise_id="E1", team_id=None)


@pytest.mark.asyncio
async def test_tokens_revoked_with_bot_token_cleans_up() -> None:
    inst = AsyncMock()
    deps = make_deps(installation_store=inst)
    await deps.key_store.set("T1", "rd-key")
    handler = _handler(deps, "tokens_revoked")

    await handler(
        event={"tokens": {"bot": ["B1"]}},
        context={"team_id": "T1", "enterprise_id": None},
        ack=AsyncMock(),
    )

    inst.async_delete_all.assert_awaited_once()
    assert await deps.key_store.get("T1") is None


@pytest.mark.asyncio
async def test_tokens_revoked_user_only_is_ignored() -> None:
    inst = AsyncMock()
    deps = make_deps(installation_store=inst)
    await deps.key_store.set("T1", "rd-key")
    handler = _handler(deps, "tokens_revoked")

    await handler(
        event={"tokens": {"oauth": ["U1"]}},
        context={"team_id": "T1"},
        ack=AsyncMock(),
    )

    inst.async_delete_all.assert_not_called()
    assert await deps.key_store.get("T1") == "rd-key"
