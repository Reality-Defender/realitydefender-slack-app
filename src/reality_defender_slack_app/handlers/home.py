from __future__ import annotations

from typing import Any

from slack_bolt.app.async_app import AsyncApp

from reality_defender_slack_app.deps import Deps
from reality_defender_slack_app.views import app_home_default, app_home_first_boot


def register_home_handlers(app: AsyncApp, deps: Deps) -> None:
    @app.event("app_home_opened")
    async def show_home(client: Any, event: Any, context: Any) -> None:
        team_id = context.get("team_id")
        configured = bool(team_id) and await deps.key_store.get(team_id) is not None
        if configured:
            await app_home_default(client, event)
        else:
            await app_home_first_boot(client, event)
