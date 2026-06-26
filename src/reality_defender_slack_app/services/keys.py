from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol, cast

from reality_defender_slack_app.config import Settings
from reality_defender_slack_app.services.crypto import Cipher

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.service_resource import Table

SETUP_REQUIRED_MESSAGE = (
    "This workspace hasn't set up Reality Defender yet. "
    "Run `/setup-rd <your API key>` to get started."
)


class RDKeyStore(Protocol):
    """Per-workspace Reality Defender API key storage."""

    async def get(self, team_id: str) -> str | None: ...

    async def set(self, team_id: str, api_key: str) -> None: ...


class InMemoryRDKeyStore:
    """Ephemeral per-workspace key store for local dev.

    Keys are lost on restart and not shared across instances. Production uses the
    durable, encrypted DynamoDBRDKeyStore instead.
    """

    def __init__(self) -> None:
        self._keys: dict[str, str] = {}

    async def get(self, team_id: str) -> str | None:
        return self._keys.get(team_id)

    async def set(self, team_id: str, api_key: str) -> None:
        self._keys[team_id] = api_key


class DynamoDBRDKeyStore:
    """Durable per-workspace RD key store backed by DynamoDB.

    The key is encrypted by the injected Cipher before it is written, so the
    plaintext never lands in DynamoDB, its logs, or table exports. The table's
    partition key is `team_id`. boto3 is synchronous, so each call runs in a
    worker thread to keep the event loop free.
    """

    def __init__(self, table: Table, cipher: Cipher) -> None:
        self._table = table
        self._cipher = cipher

    async def get(self, team_id: str) -> str | None:
        response = await asyncio.to_thread(
            self._table.get_item, Key={"team_id": team_id}
        )
        item = response.get("Item")
        if not item:
            return None
        return await self._cipher.decrypt(cast(str, item["encrypted_key"]))

    async def set(self, team_id: str, api_key: str) -> None:
        encrypted = await self._cipher.encrypt(api_key)
        await asyncio.to_thread(
            self._table.put_item,
            Item={"team_id": team_id, "encrypted_key": encrypted},
        )


async def resolve_api_key(
    store: RDKeyStore, team_id: str | None, settings: Settings
) -> str | None:
    """Resolve a workspace's RD key.

    Prefers the workspace's own key; falls back to the shared dev key only when
    one is configured (local dev). In production the shared key is left unset, so
    a workspace without its own key resolves to None rather than silently billing
    the operator's account.
    """
    if team_id:
        key = await store.get(team_id)
        if key:
            return key
    return settings.reality_defender_api_key
