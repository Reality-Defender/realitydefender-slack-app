from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast
from unittest.mock import AsyncMock

from reality_defender_slack_app.config import Settings
from reality_defender_slack_app.deps import Deps
from reality_defender_slack_app.services.keys import InMemoryRDKeyStore
from reality_defender_slack_app.services.reality_defender import RDClient

if TYPE_CHECKING:
    from slack_sdk.oauth.installation_store.async_installation_store import (
        AsyncInstallationStore,
    )


class HandlerRecorder:
    """Captures handlers registered via @app.command / .event / .shortcut.

    Stand-in for AsyncApp so handler closures can be retrieved and called
    directly in tests without a running Bolt app.
    """

    def __init__(self) -> None:
        self.handlers: dict[tuple[str, str], Callable[..., Any]] = {}

    def _register(self, kind: str, name: str) -> Callable[..., Any]:
        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            self.handlers[(kind, name)] = fn
            return fn

        return deco

    def command(self, name: str) -> Callable[..., Any]:
        return self._register("command", name)

    def event(self, name: str) -> Callable[..., Any]:
        return self._register("event", name)

    def shortcut(self, name: str) -> Callable[..., Any]:
        return self._register("shortcut", name)


def make_deps(
    *,
    shared_key: str | None = None,
    installation_store: AsyncInstallationStore | None = None,
) -> Deps:
    """Build a Deps with a real in-memory key store and a mocked RD client."""
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        slack_client_id="id",
        slack_client_secret="secret",
        slack_signing_secret="signing",
        reality_defender_api_key=shared_key,
    )
    return Deps(
        settings=settings,
        rd_client=cast(RDClient, AsyncMock()),
        key_store=InMemoryRDKeyStore(),
        installation_store=installation_store
        or cast("AsyncInstallationStore", AsyncMock()),
    )
