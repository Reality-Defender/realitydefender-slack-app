from __future__ import annotations

import asyncio
import json
import logging
import time
from logging import Logger
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

from slack_sdk.oauth.installation_store.async_installation_store import (
    AsyncInstallationStore,
)
from slack_sdk.oauth.installation_store.models.bot import Bot
from slack_sdk.oauth.installation_store.models.installation import Installation
from slack_sdk.oauth.state_store.async_state_store import AsyncOAuthStateStore

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.service_resource import Table


def _workspace_pk(enterprise_id: str | None, team_id: str | None) -> str:
    """Partition key for a workspace / org installation."""
    return f"{enterprise_id or 'none'}-{team_id or 'none'}"


class DynamoDBInstallationStore(AsyncInstallationStore):
    """Bot-only slack_sdk InstallationStore backed by a single DynamoDB table.

    The app requests bot scopes only, so Bolt is configured with
    installation_store_bot_only=True and authorizes via find_bot. We therefore
    store just the workspace bot token — no per-user installer records.

    Layout: pk = "{enterprise_id}-{team_id}", sk = "bot-latest",
    payload = the Bot model's __dict__ as a JSON string (which sidesteps
    DynamoDB's Decimal/number coercion). boto3 is synchronous, so all calls run
    in a worker thread to keep the event loop free.
    """

    def __init__(self, table: Table, *, logger: Logger | None = None) -> None:
        self._table = table
        self._logger = logger or logging.getLogger(__name__)

    @property
    def logger(self) -> Logger:
        return self._logger

    async def _put(self, pk: str, sk: str, payload: dict[str, Any]) -> None:
        await asyncio.to_thread(
            self._table.put_item,
            Item={"pk": pk, "sk": sk, "payload": json.dumps(payload)},
        )

    async def _get(self, pk: str, sk: str) -> dict[str, Any] | None:
        response = await asyncio.to_thread(self._table.get_item, Key={"pk": pk, "sk": sk})
        item = response.get("Item")
        if not item:
            return None
        return cast("dict[str, Any]", json.loads(cast(str, item["payload"])))

    async def async_save(self, installation: Installation) -> None:
        # Bot-only: persist just the bot installation, not per-user records.
        bot = installation.to_bot()
        # bot_token is typed str but is None at runtime for token-less installs.
        if not bot.bot_token:
            self.logger.debug("Skipped saving a bot installation without a bot token")
            return
        pk = _workspace_pk(bot.enterprise_id, bot.team_id)
        await self._put(pk, "bot-latest", bot.__dict__)

    async def async_find_bot(
        self,
        *,
        enterprise_id: str | None,
        team_id: str | None,
        is_enterprise_install: bool | None = False,
    ) -> Bot | None:
        if is_enterprise_install:
            team_id = None
        data = await self._get(_workspace_pk(enterprise_id, team_id), "bot-latest")
        return Bot(**data) if data else None

    async def async_delete_bot(
        self, *, enterprise_id: str | None, team_id: str | None
    ) -> None:
        pk = _workspace_pk(enterprise_id, team_id)
        await asyncio.to_thread(self._table.delete_item, Key={"pk": pk, "sk": "bot-latest"})

    async def async_delete_all(
        self, *, enterprise_id: str | None, team_id: str | None
    ) -> None:
        """Delete a workspace / org installation. Bot-only: same as delete_bot."""
        await self.async_delete_bot(enterprise_id=enterprise_id, team_id=team_id)


class DynamoDBOAuthStateStore(AsyncOAuthStateStore):
    """slack_sdk OAuthStateStore backed by DynamoDB.

    Each state is one item keyed by `state`, with an `expire_at` epoch-seconds
    attribute. Configure DynamoDB TTL on `expire_at` for automatic cleanup;
    `async_consume` also checks expiry explicitly because TTL deletion lags.
    """

    def __init__(
        self,
        table: Table,
        *,
        expiration_seconds: int = 600,
        logger: Logger | None = None,
    ) -> None:
        self._table = table
        self._expiration_seconds = expiration_seconds
        self._logger = logger or logging.getLogger(__name__)

    @property
    def logger(self) -> Logger:
        return self._logger

    async def async_issue(self, *args: Any, **kwargs: Any) -> str:
        state = str(uuid4())
        expire_at = int(time.time()) + self._expiration_seconds
        await asyncio.to_thread(
            self._table.put_item, Item={"state": state, "expire_at": expire_at}
        )
        return state

    async def async_consume(self, state: str) -> bool:
        response = await asyncio.to_thread(self._table.get_item, Key={"state": state})
        item = response.get("Item")
        if not item:
            return False
        # One-time use: delete regardless of expiry.
        await asyncio.to_thread(self._table.delete_item, Key={"state": state})
        return int(item["expire_at"]) >= int(time.time())  # type: ignore[arg-type]
