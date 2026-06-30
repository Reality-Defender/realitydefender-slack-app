import boto3
import pytest
from moto import mock_aws

from reality_defender_slack_app.services.crypto import KMSCipher, NoOpCipher


@pytest.mark.asyncio
async def test_noop_cipher_round_trip() -> None:
    cipher = NoOpCipher()
    assert await cipher.encrypt("secret") == "secret"
    assert await cipher.decrypt("secret") == "secret"


@pytest.mark.asyncio
async def test_kms_cipher_round_trip() -> None:
    with mock_aws():
        kms = boto3.client("kms", region_name="us-east-1")
        key_id = kms.create_key()["KeyMetadata"]["KeyId"]
        cipher = KMSCipher(key_id, client=kms)

        ciphertext = await cipher.encrypt("rd-secret-key")
        assert ciphertext != "rd-secret-key"  # actually encrypted
        assert await cipher.decrypt(ciphertext) == "rd-secret-key"
