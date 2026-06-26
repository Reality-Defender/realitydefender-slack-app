from __future__ import annotations

from slack_bolt.app.async_app import AsyncApp

from reality_defender_slack_app.deps import Deps
from reality_defender_slack_app.handlers.commands import register_command_handlers
from reality_defender_slack_app.handlers.home import register_home_handlers
from reality_defender_slack_app.handlers.lifecycle import register_lifecycle_handlers
from reality_defender_slack_app.handlers.mentions import register_mention_handlers
from reality_defender_slack_app.handlers.shortcuts import register_shortcut_handlers


def register_handlers(app: AsyncApp, deps: Deps) -> None:
    """Register all Slack handlers on the Bolt app."""
    register_command_handlers(app, deps)
    register_mention_handlers(app, deps)
    register_shortcut_handlers(app, deps)
    register_home_handlers(app, deps)
    register_lifecycle_handlers(app, deps)
