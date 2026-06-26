from __future__ import annotations

from dataclasses import dataclass

from reality_defender_slack_app.config import Settings
from reality_defender_slack_app.services.keys import RDKeyStore
from reality_defender_slack_app.services.reality_defender import RDClient
from reality_defender_slack_app.services.tracker import AnalysisTracker


@dataclass
class Deps:
    """Shared services handed to the Slack handlers."""

    settings: Settings
    rd_client: RDClient
    key_store: RDKeyStore
    tracker: AnalysisTracker
