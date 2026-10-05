import pytest

from reality_defender_slack_app.services import reality_defender as rd_mod


class _FakeRD:
    """Stand-in for the RealityDefender SDK client."""

    uploaded_name = ""

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key
        self.client = None

    async def upload_social_media(self, social_media_link: str) -> dict:
        return {"request_id": "req-social", "media_id": "media-social"}

    async def upload(self, file_path: str) -> dict:
        _FakeRD.uploaded_name = file_path.rsplit("/", 1)[-1]
        return {"request_id": "req-file", "media_id": "media-file"}

    async def get_result(self, request_id: str, max_attempts: int, polling_interval: int) -> dict:
        return {"status": "AUTHENTIC", "score": 0.05, "models": []}

    async def cleanup(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _patch_rd(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rd_mod, "RealityDefender", _FakeRD)

    async def _raw(client: object, request_id: str) -> dict:
        return {"requestId": request_id}

    monkeypatch.setattr(rd_mod, "get_media_result", _raw)


@pytest.mark.asyncio
async def test_analyze_url_passes_key_and_returns_media_id() -> None:
    analysis = await rd_mod.RDClient().analyze_url("rd-key", "https://x.com/a/status/1")

    assert analysis.result["status"] == "AUTHENTIC"
    assert analysis.media_id == "media-social"
    assert analysis.request_id == "req-social"
    assert analysis.raw == {"requestId": "req-social"}


@pytest.mark.asyncio
async def test_analyze_file_bytes_returns_media_id() -> None:
    analysis = await rd_mod.RDClient().analyze_file_bytes(
        "rd-key", b"\x89PNG", "my pic/../(1).png"
    )

    assert analysis.result["status"] == "AUTHENTIC"
    assert analysis.media_id == "media-file"
    # Uploaded under the user's (sanitized) filename, not a random temp name.
    assert _FakeRD.uploaded_name == "_1_.png"
