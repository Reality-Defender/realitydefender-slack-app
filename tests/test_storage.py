from collections.abc import Iterator

import pytest
from moto import mock_aws

from reality_defender_slack_app.config import Settings
from reality_defender_slack_app.services.installation_store import (
    DynamoDBInstallationStore,
    DynamoDBOAuthStateStore,
)
from reality_defender_slack_app.services.keys import (
    DynamoDBRDKeyStore,
    InMemoryRDKeyStore,
)
from reality_defender_slack_app.services.storage import build_storage


@pytest.fixture
def aws() -> Iterator[None]:
    with mock_aws():
        yield


def _settings(
    *,
    aws_region: str | None = None,
    dynamodb_installations_table: str | None = None,
    dynamodb_oauth_states_table: str | None = None,
    dynamodb_rd_keys_table: str | None = None,
    rd_key_kms_key_id: str | None = None,
) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        slack_client_id="id",
        slack_client_secret="secret",
        slack_signing_secret="signing",
        aws_region=aws_region,
        dynamodb_installations_table=dynamodb_installations_table,
        dynamodb_oauth_states_table=dynamodb_oauth_states_table,
        dynamodb_rd_keys_table=dynamodb_rd_keys_table,
        rd_key_kms_key_id=rd_key_kms_key_id,
    )


def _dynamodb_settings(*, rd_key_kms_key_id: str | None) -> Settings:
    return _settings(
        aws_region="us-east-1",
        dynamodb_installations_table="installs",
        dynamodb_oauth_states_table="states",
        dynamodb_rd_keys_table="rd-keys",
        rd_key_kms_key_id=rd_key_kms_key_id,
    )


def test_build_storage_local_by_default() -> None:
    storage = build_storage(_settings())
    assert isinstance(storage.key_store, InMemoryRDKeyStore)


def test_build_storage_dynamodb(aws: None) -> None:
    storage = build_storage(_dynamodb_settings(rd_key_kms_key_id="alias/rd-key"))
    assert isinstance(storage.key_store, DynamoDBRDKeyStore)
    assert isinstance(storage.installation_store, DynamoDBInstallationStore)
    assert isinstance(storage.state_store, DynamoDBOAuthStateStore)


def test_build_storage_requires_kms_when_dynamodb() -> None:
    with pytest.raises(ValueError, match="kms"):
        build_storage(_dynamodb_settings(rd_key_kms_key_id=None))
