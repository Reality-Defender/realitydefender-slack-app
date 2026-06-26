from collections.abc import Iterator
from typing import TYPE_CHECKING

import boto3
import pytest
from moto import mock_aws
from slack_sdk.oauth.installation_store.models.installation import Installation

from reality_defender_slack_app.services.crypto import KMSCipher
from reality_defender_slack_app.services.installation_store import (
    DynamoDBInstallationStore,
    DynamoDBOAuthStateStore,
)
from reality_defender_slack_app.services.keys import DynamoDBRDKeyStore

if TYPE_CHECKING:
    from mypy_boto3_dynamodb.service_resource import DynamoDBServiceResource, Table

REGION = "us-east-1"


@pytest.fixture
def aws() -> Iterator[None]:
    with mock_aws():
        yield


def _dynamodb() -> "DynamoDBServiceResource":
    return boto3.resource("dynamodb", region_name=REGION)


def _make_keys_table() -> "Table":
    db = _dynamodb()
    db.create_table(
        TableName="rd-keys",
        KeySchema=[{"AttributeName": "team_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "team_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    return db.Table("rd-keys")


def _make_installs_table() -> "Table":
    db = _dynamodb()
    db.create_table(
        TableName="installs",
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    return db.Table("installs")


def _make_states_table() -> "Table":
    db = _dynamodb()
    db.create_table(
        TableName="states",
        KeySchema=[{"AttributeName": "state", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "state", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    return db.Table("states")


def _cipher() -> KMSCipher:
    kms = boto3.client("kms", region_name=REGION)
    key_id = kms.create_key()["KeyMetadata"]["KeyId"]
    return KMSCipher(key_id, client=kms)


@pytest.mark.asyncio
async def test_rd_key_store_round_trip(aws: None) -> None:
    table = _make_keys_table()
    store = DynamoDBRDKeyStore(table, _cipher())

    assert await store.get("T1") is None

    await store.set("T1", "rd-key-1")
    assert await store.get("T1") == "rd-key-1"
    assert await store.get("T2") is None


@pytest.mark.asyncio
async def test_rd_key_store_delete(aws: None) -> None:
    table = _make_keys_table()
    store = DynamoDBRDKeyStore(table, _cipher())
    await store.set("T1", "rd-key-1")

    await store.delete("T1")
    assert await store.get("T1") is None


@pytest.mark.asyncio
async def test_rd_key_store_encrypts_at_rest(aws: None) -> None:
    table = _make_keys_table()
    store = DynamoDBRDKeyStore(table, _cipher())

    await store.set("T1", "rd-secret")

    # The stored value must not be the plaintext key.
    raw = table.get_item(Key={"team_id": "T1"})["Item"]
    assert raw["encrypted_key"] != "rd-secret"


def _installation(*, team_id: str = "T1", user_id: str = "U1") -> Installation:
    return Installation(
        app_id="A1",
        enterprise_id=None,
        team_id=team_id,
        user_id=user_id,
        bot_token="xoxb-123",
        bot_id="B1",
        bot_user_id="UB1",
        bot_scopes=["chat:write"],
    )


@pytest.mark.asyncio
async def test_installation_store_save_and_find_bot(aws: None) -> None:
    store = DynamoDBInstallationStore(_make_installs_table())
    await store.async_save(_installation())

    bot = await store.async_find_bot(enterprise_id=None, team_id="T1")
    assert bot is not None
    assert bot.bot_token == "xoxb-123"


@pytest.mark.asyncio
async def test_installation_store_saves_bot_only(aws: None) -> None:
    # Bot-only: async_save must persist exactly one item (bot-latest), no
    # per-user installer records.
    table = _make_installs_table()
    store = DynamoDBInstallationStore(table)
    await store.async_save(_installation())

    items = table.scan()["Items"]
    assert [item["sk"] for item in items] == ["bot-latest"]


@pytest.mark.asyncio
async def test_installation_store_find_missing(aws: None) -> None:
    store = DynamoDBInstallationStore(_make_installs_table())
    assert await store.async_find_bot(enterprise_id=None, team_id="nope") is None


@pytest.mark.asyncio
async def test_installation_store_delete_all(aws: None) -> None:
    store = DynamoDBInstallationStore(_make_installs_table())
    await store.async_save(_installation())

    await store.async_delete_all(enterprise_id=None, team_id="T1")

    assert await store.async_find_bot(enterprise_id=None, team_id="T1") is None


@pytest.mark.asyncio
async def test_state_store_issue_and_consume(aws: None) -> None:
    store = DynamoDBOAuthStateStore(_make_states_table())

    state = await store.async_issue()
    assert isinstance(state, str) and state

    assert await store.async_consume(state) is True
    # State is single-use.
    assert await store.async_consume(state) is False


@pytest.mark.asyncio
async def test_state_store_unknown_state(aws: None) -> None:
    store = DynamoDBOAuthStateStore(_make_states_table())
    assert await store.async_consume("never-issued") is False


@pytest.mark.asyncio
async def test_state_store_expired(aws: None) -> None:
    # Negative expiration makes every issued state already expired.
    store = DynamoDBOAuthStateStore(_make_states_table(), expiration_seconds=-1)
    state = await store.async_issue()
    assert await store.async_consume(state) is False
