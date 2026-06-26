from __future__ import annotations

import asyncio
import base64
from typing import TYPE_CHECKING, Protocol

import boto3

if TYPE_CHECKING:
    from mypy_boto3_kms.client import KMSClient


class Cipher(Protocol):
    """Encrypts/decrypts small secrets (e.g. RD API keys) at the app layer.

    Keeping this behind a Protocol means the storage layer never depends on a
    specific crypto backend, mirroring the storage-interface design constraint.
    """

    async def encrypt(self, plaintext: str) -> str: ...

    async def decrypt(self, ciphertext: str) -> str: ...


class NoOpCipher:
    """Pass-through cipher for local dev. Does NOT encrypt — never use in prod."""

    async def encrypt(self, plaintext: str) -> str:
        return plaintext

    async def decrypt(self, ciphertext: str) -> str:
        return ciphertext


class KMSCipher:
    """AWS KMS encryption for values under 4 KB (RD API keys qualify).

    Calls KMS Encrypt/Decrypt directly — no envelope/data-key needed at this
    size — and stores the ciphertext as a base64 string. boto3 is synchronous,
    so each call runs in a worker thread to avoid blocking the event loop.
    """

    def __init__(
        self,
        key_id: str,
        *,
        region_name: str | None = None,
        client: KMSClient | None = None,
    ) -> None:
        self._key_id = key_id
        self._client = client or boto3.client("kms", region_name=region_name)

    async def encrypt(self, plaintext: str) -> str:
        response = await asyncio.to_thread(
            self._client.encrypt,
            KeyId=self._key_id,
            Plaintext=plaintext.encode("utf-8"),
        )
        return base64.b64encode(response["CiphertextBlob"]).decode("ascii")

    async def decrypt(self, ciphertext: str) -> str:
        blob = base64.b64decode(ciphertext)
        response = await asyncio.to_thread(
            self._client.decrypt,
            CiphertextBlob=blob,
        )
        return response["Plaintext"].decode("utf-8")
