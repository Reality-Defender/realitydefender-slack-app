import pytest

from reality_defender_slack_app.config import Settings
from reality_defender_slack_app.services.keys import InMemoryRDKeyStore, resolve_api_key


def _settings(*, allow_shared: bool, shared_key: str | None) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        slack_client_id="id",
        slack_client_secret="secret",
        slack_signing_secret="signing",
        reality_defender_api_key=shared_key,
        allow_shared_rd_key=allow_shared,
    )


@pytest.mark.asyncio
async def test_in_memory_store_get_set() -> None:
    store = InMemoryRDKeyStore()
    assert await store.get("T1") is None

    await store.set("T1", "rd-key-1")
    assert await store.get("T1") == "rd-key-1"
    assert await store.get("T2") is None


@pytest.mark.asyncio
async def test_resolve_prefers_workspace_key() -> None:
    store = InMemoryRDKeyStore()
    await store.set("T1", "workspace-key")
    settings = _settings(allow_shared=True, shared_key="shared-key")

    assert await resolve_api_key(store, "T1", settings) == "workspace-key"


@pytest.mark.asyncio
async def test_resolve_falls_back_to_shared_when_allowed() -> None:
    store = InMemoryRDKeyStore()
    settings = _settings(allow_shared=True, shared_key="shared-key")

    assert await resolve_api_key(store, "T1", settings) == "shared-key"


@pytest.mark.asyncio
async def test_resolve_returns_none_when_shared_disallowed() -> None:
    store = InMemoryRDKeyStore()
    settings = _settings(allow_shared=False, shared_key="shared-key")

    assert await resolve_api_key(store, "T1", settings) is None
