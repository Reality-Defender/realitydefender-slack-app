from __future__ import annotations

import logging
from typing import Any

from slack_bolt.app.async_app import AsyncApp

from reality_defender_slack_app.deps import Deps

logger = logging.getLogger(__name__)


def register_lifecycle_handlers(app: AsyncApp, deps: Deps) -> None:
    """Handle uninstall / token-revocation so we don't retain dead tokens.

    Slack Marketplace requires apps to delete a workspace's tokens when it
    uninstalls. We also drop the workspace's stored Reality Defender API key —
    a customer secret that must not outlive the installation.

    Bolt skips the auth test for these events (the token is already gone), so
    the handlers run with team/enterprise ids resolved from the event envelope.
    """

    @app.event("app_uninstalled")
    async def handle_app_uninstalled(context: Any, ack: Any) -> None:
        await ack()
        await _cleanup_workspace(deps, context)

    @app.event("tokens_revoked")
    async def handle_tokens_revoked(event: Any, context: Any, ack: Any) -> None:
        await ack()
        # Bot-only app: only a revoked bot token kills the install. Ignore
        # user-token-only revocations — we don't store those.
        if event.get("tokens", {}).get("bot"):
            await _cleanup_workspace(deps, context)


async def _cleanup_workspace(deps: Deps, context: Any) -> None:
    enterprise_id = context.get("enterprise_id")
    team_id = context.get("team_id")
    try:
        await deps.installation_store.async_delete_all(
            enterprise_id=enterprise_id, team_id=team_id
        )
        # Keys are partitioned by team_id; org-wide installs have none to drop.
        if team_id:
            await deps.key_store.delete(team_id)
        logger.info(
            "Cleaned up installation and RD key (team=%s enterprise=%s)",
            team_id,
            enterprise_id,
        )
    except Exception:
        logger.exception(
            "Failed to clean up workspace (team=%s enterprise=%s)",
            team_id,
            enterprise_id,
        )
