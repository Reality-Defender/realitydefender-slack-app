from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from reality_defender_slack_app.config import Settings
from reality_defender_slack_app.services.keys import RDKeyStore
from reality_defender_slack_app.services.reality_defender import RDClient

if TYPE_CHECKING:
    from slack_sdk.oauth.installation_store.async_installation_store import (
        AsyncInstallationStore,
    )


@dataclass
class Deps:
    """Shared services handed to the Slack handlers."""

    settings: Settings
    rd_client: RDClient
    key_store: RDKeyStore
    installation_store: AsyncInstallationStore
