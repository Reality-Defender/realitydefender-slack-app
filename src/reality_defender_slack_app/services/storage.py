from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import boto3

from reality_defender_slack_app.config import Settings
from reality_defender_slack_app.services.crypto import KMSCipher
from reality_defender_slack_app.services.installation_store import (
    DynamoDBInstallationStore,
    DynamoDBOAuthStateStore,
)
from reality_defender_slack_app.services.keys import (
    DynamoDBRDKeyStore,
    InMemoryRDKeyStore,
    RDKeyStore,
)

if TYPE_CHECKING:
    from slack_sdk.oauth.installation_store.async_installation_store import (
        AsyncInstallationStore,
    )
    from slack_sdk.oauth.state_store.async_state_store import AsyncOAuthStateStore

# Local-dev file stores live here so the OAuth flow works without AWS.
INSTALLATION_DIR = "./data/installations"
STATE_DIR = "./data/states"

OAUTH_STATE_EXPIRATION_SECONDS = 600


@dataclass
class Storage:
    """The three persistence backends the app wires into Bolt + Deps."""

    key_store: RDKeyStore
    installation_store: AsyncInstallationStore
    state_store: AsyncOAuthStateStore


def build_storage(settings: Settings) -> Storage:
    """Build durable DynamoDB stores in production, file/in-memory otherwise.

    Selection is driven by config: when all DynamoDB tables are set we run in
    production mode; otherwise we fall back to ephemeral stores so local dev
    needs no AWS.
    """
    if settings.dynamodb_enabled:
        return _build_dynamodb_storage(settings)
    return _build_local_storage()


def _build_dynamodb_storage(settings: Settings) -> Storage:
    if not settings.rd_key_kms_key_id:
        raise ValueError(
            "rd_key_kms_key_id is required when DynamoDB storage is enabled: "
            "RD API keys must be encrypted at rest."
        )

    # dynamodb_enabled guarantees these are set; assert narrows them for mypy.
    assert settings.dynamodb_rd_keys_table is not None
    assert settings.dynamodb_installations_table is not None
    assert settings.dynamodb_oauth_states_table is not None

    dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
    cipher = KMSCipher(settings.rd_key_kms_key_id, region_name=settings.aws_region)

    return Storage(
        key_store=DynamoDBRDKeyStore(
            dynamodb.Table(settings.dynamodb_rd_keys_table), cipher
        ),
        installation_store=DynamoDBInstallationStore(
            dynamodb.Table(settings.dynamodb_installations_table)
        ),
        state_store=DynamoDBOAuthStateStore(
            dynamodb.Table(settings.dynamodb_oauth_states_table),
            expiration_seconds=OAUTH_STATE_EXPIRATION_SECONDS,
        ),
    )


def _build_local_storage() -> Storage:
    # Imported lazily so the default (DynamoDB) path doesn't pull these in.
    from slack_sdk.oauth.installation_store import FileInstallationStore
    from slack_sdk.oauth.state_store import FileOAuthStateStore

    return Storage(
        key_store=InMemoryRDKeyStore(),
        installation_store=FileInstallationStore(base_dir=INSTALLATION_DIR),
        state_store=FileOAuthStateStore(
            expiration_seconds=OAUTH_STATE_EXPIRATION_SECONDS, base_dir=STATE_DIR
        ),
    )
