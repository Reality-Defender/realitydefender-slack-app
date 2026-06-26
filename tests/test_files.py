from typing import Any
from unittest.mock import AsyncMock

import pytest

from reality_defender_slack_app.handlers import files
from reality_defender_slack_app.services.keys import SETUP_REQUIRED_MESSAGE
from tests.helpers import make_deps


def _file_info(mimetype: str, *, shares_ts: str = "100.1") -> dict[str, Any]:
    return {
        "file": {
            "name": "clip.mp4",
            "mimetype": mimetype,
            "url_private_download": "https://files.slack.com/clip.mp4",
            "shares": {"public": {"C1": [{"ts": shares_ts}]}},
        }
    }


def _posted_texts(client: AsyncMock) -> list[str]:
    return [c.kwargs["text"] for c in client.chat_postMessage.call_args_list]


@pytest.mark.asyncio
async def test_process_file_unsupported_mimetype(monkeypatch: pytest.MonkeyPatch) -> None:
    analyze = AsyncMock()
    monkeypatch.setattr(files, "analyze_file_and_post", analyze)
    client = AsyncMock()
    client.files_info = AsyncMock(return_value=_file_info("application/zip"))

    await files._process_file(
        make_deps(shared_key="k"),
        client,
        {"team_id": "T1", "bot_token": "xoxb"},
        file_id="F1",
        channel_id="C1",
    )

    assert any("Unsupported file type" in t for t in _posted_texts(client))
    analyze.assert_not_called()


@pytest.mark.asyncio
async def test_process_file_without_key_prompts_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analyze = AsyncMock()
    monkeypatch.setattr(files, "analyze_file_and_post", analyze)
    client = AsyncMock()
    client.files_info = AsyncMock(return_value=_file_info("image/png"))

    await files._process_file(
        make_deps(shared_key=None),
        client,
        {"team_id": "T1", "bot_token": "xoxb"},
        file_id="F1",
        channel_id="C1",
    )

    assert SETUP_REQUIRED_MESSAGE in _posted_texts(client)
    analyze.assert_not_called()


@pytest.mark.asyncio
async def test_process_file_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    download = AsyncMock(return_value=b"\x89PNG")
    analyze = AsyncMock()
    monkeypatch.setattr(files, "download_slack_file", download)
    monkeypatch.setattr(files, "analyze_file_and_post", analyze)
    client = AsyncMock()
    client.files_info = AsyncMock(return_value=_file_info("image/png", shares_ts="200.2"))

    await files._process_file(
        make_deps(shared_key="k"),
        client,
        {"team_id": "T1", "bot_token": "xoxb"},
        file_id="F1",
        channel_id="C1",
    )

    download.assert_awaited_once()
    analyze.assert_awaited_once()
    kwargs = analyze.call_args.kwargs
    assert kwargs["filename"] == "clip.mp4"
    assert kwargs["content"] == b"\x89PNG"
    assert kwargs["channel_id"] == "C1"
    assert kwargs["thread_ts"] == "200.2"  # resolved from shares
