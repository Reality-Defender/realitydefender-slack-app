import pytest

from reality_defender_slack_app.services import reality_defender as rd_mod


class _FakeRD:
    """Stand-in for the RealityDefender SDK client."""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def upload_social_media(self, social_media_link: str) -> dict:
        return {"request_id": "req-social", "media_id": "media-social"}

    async def upload(self, file_path: str) -> dict:
        return {"request_id": "req-file", "media_id": "media-file"}

    async def get_result(self, request_id: str, max_attempts: int, polling_interval: int) -> dict:
        return {"status": "AUTHENTIC", "score": 0.05, "models": []}

    async def cleanup(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _patch_rd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rd_mod, "RealityDefender", _FakeRD)


@pytest.mark.asyncio
async def test_analyze_url_passes_key_and_returns_media_id() -> None:
    result, media_id = await rd_mod.RDClient().analyze_url("rd-key", "https://x.com/a/status/1")

    assert result["status"] == "AUTHENTIC"
    assert media_id == "media-social"


@pytest.mark.asyncio
async def test_analyze_file_bytes_returns_media_id() -> None:
    result, media_id = await rd_mod.RDClient().analyze_file_bytes("rd-key", b"\x89PNG", "pic.png")

    assert result["status"] == "AUTHENTIC"
    assert media_id == "media-file"
