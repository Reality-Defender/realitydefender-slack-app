from __future__ import annotations

from typing import Protocol

from reality_defender_slack_app.config import Settings

SETUP_REQUIRED_MESSAGE = (
    "This workspace hasn't set up Reality Defender yet. "
    "Run `/setup-rd <your API key>` to get started."
)


class RDKeyStore(Protocol):
    """Per-workspace Reality Defender API key storage."""

    async def get(self, team_id: str) -> str | None: ...

    async def set(self, team_id: str, api_key: str) -> None: ...


class InMemoryRDKeyStore:
    """Ephemeral per-workspace key store.

    Phase B placeholder — replaced by a durable, encrypted DynamoDB store in
    Phase C. Keys are lost on restart and not shared across instances.
    """

    def __init__(self) -> None:
        self._keys: dict[str, str] = {}

    async def get(self, team_id: str) -> str | None:
        return self._keys.get(team_id)

    async def set(self, team_id: str, api_key: str) -> None:
        self._keys[team_id] = api_key


async def resolve_api_key(
    store: RDKeyStore, team_id: str | None, settings: Settings
) -> str | None:
    """Resolve a workspace's RD key, falling back to the shared dev key if allowed."""
    if team_id:
        key = await store.get(team_id)
        if key:
            return key
    if settings.allow_shared_rd_key:
        return settings.reality_defender_api_key
    return None
