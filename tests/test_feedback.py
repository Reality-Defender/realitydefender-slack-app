"""'Report an issue', end to end through Bolt and the real RD SDK.

Requests go through Bolt's real dispatch (so listener wiring and argument
injection are exercised) and the real RDClient/SDK, stubbing only the network:
Slack Web API calls and the SDK's HTTP POST.
"""

import json
from collections.abc import Sequence
from typing import Any
from unittest.mock import AsyncMock
from urllib.parse import urlencode

import pytest
from realitydefender.client.http_client import HttpClient
from realitydefender.errors import RealityDefenderError
from slack_bolt.app.async_app import AsyncApp
from slack_bolt.authorization import AuthorizeResult
from slack_bolt.request.async_request import AsyncBoltRequest
from slack_sdk.web.async_client import AsyncWebClient

from reality_defender_slack_app.handlers import feedback
from reality_defender_slack_app.services.formatting import result_blocks
from reality_defender_slack_app.services.reality_defender import RDClient
from reality_defender_slack_app.views import REPORT_VIEW_ID
from tests.helpers import make_deps

FEEDBACK_RESPONSE = {
    "id": "fb-1",
    "userId": "u-1",
    "requestId": "req-1",
    "institutionId": "inst-1",
    "category": "FALSE_POSITIVE",
    "label": "REAL",
    "createdAt": "2026-10-05T00:00:00Z",
}


@pytest.fixture
def slack(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    calls = {"views_open": AsyncMock(), "chat_postEphemeral": AsyncMock()}
    for name, mock in calls.items():
        monkeypatch.setattr(AsyncWebClient, name, mock)
    return calls


@pytest.fixture
def rd_post(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    post = AsyncMock(return_value=FEEDBACK_RESPONSE)
    monkeypatch.setattr(HttpClient, "post", post)
    return post


def _app(shared_key: str | None = "rd-key") -> AsyncApp:
    async def authorize(**_: Any) -> AuthorizeResult:
        return AuthorizeResult(enterprise_id=None, team_id="T1", bot_token="xoxb-1")

    app = AsyncApp(
        signing_secret="secret",
        authorize=authorize,
        request_verification_enabled=False,
        # Run listeners to completion before responding, so tests can assert.
        process_before_response=True,
    )
    deps = make_deps(shared_key=shared_key)
    deps.rd_client = RDClient()
    feedback.register_feedback_handlers(app, deps)
    return app


async def _send(app: AsyncApp, payload: dict[str, Any]) -> Any:
    body = urlencode({"payload": json.dumps(payload)})
    headers: dict[str, str | Sequence[str]] = {
        "content-type": "application/x-www-form-urlencoded"
    }
    return await app.async_dispatch(AsyncBoltRequest(body=body, headers=headers))


def _button_click() -> dict[str, Any]:
    """block_actions payload for the button as result_blocks() renders it."""
    button = result_blocks("RESULT", "req-1", "MANIPULATED")[1]["elements"][0]
    return {
        "type": "block_actions",
        "team": {"id": "T1"},
        "user": {"id": "U1", "name": "jane", "team_id": "T1"},
        "api_app_id": "A1",
        "trigger_id": "tg-1",
        "channel": {"id": "C1"},
        "message": {"ts": "2.2", "thread_ts": "1.1"},
        "actions": [{**button, "block_id": "b1", "action_ts": "3.3"}],
    }


def _submission(choice: str | None, details: str = "") -> dict[str, Any]:
    selected = {"selected_option": {"value": choice}} if choice else {}
    return {
        "type": "view_submission",
        "team": {"id": "T1"},
        "user": {"id": "U1", "name": "jane", "team_id": "T1"},
        "api_app_id": "A1",
        "view": {
            "id": "V1",
            "type": "modal",
            "callback_id": REPORT_VIEW_ID,
            "private_metadata": json.dumps(
                {
                    "request_id": "req-1",
                    "status": "MANIPULATED",
                    "channel_id": "C1",
                    "thread_ts": "1.1",
                }
            ),
            "state": {
                "values": {
                    "issue": {"choice": selected},
                    "details": {"text": {"value": details}},
                }
            },
        },
    }


@pytest.mark.asyncio
async def test_button_opens_form_with_thread_metadata(
    slack: dict[str, AsyncMock],
) -> None:
    resp = await _send(_app(), _button_click())

    assert resp.status == 200
    kwargs = slack["views_open"].call_args.kwargs
    assert kwargs["trigger_id"] == "tg-1"
    assert kwargs["view"]["callback_id"] == REPORT_VIEW_ID
    assert json.loads(kwargs["view"]["private_metadata"]) == {
        "request_id": "req-1",
        "status": "MANIPULATED",
        "channel_id": "C1",
        "thread_ts": "1.1",
    }


@pytest.mark.asyncio
async def test_submit_posts_feedback_to_rd_v2_api(
    slack: dict[str, AsyncMock], rd_post: AsyncMock
) -> None:
    resp = await _send(_app(), _submission("false_positive", "It's my own photo"))

    assert resp.status == 200
    rd_post.assert_awaited_once()
    path = rd_post.call_args.args[0]
    assert path == "/api/v2/user-feedback"
    # Matches CreateUserFeedbackV2ReqDto (eng-os realscan backend).
    assert rd_post.call_args.kwargs["json"] == {
        "requestId": "req-1",
        "label": "REAL",
        "feedbackCategory": "FALSE_POSITIVE",
        "comment": "Reported from Slack by jane (U1).\nIt's my own photo",
    }
    ephemeral = slack["chat_postEphemeral"].call_args.kwargs
    assert ephemeral["channel"] == "C1"
    assert ephemeral["user"] == "U1"
    assert ephemeral["thread_ts"] == "1.1"
    assert ephemeral["text"].startswith(":white_check_mark:")


@pytest.mark.asyncio
async def test_confirmation_label_follows_the_verdict(
    slack: dict[str, AsyncMock], rd_post: AsyncMock
) -> None:
    await _send(_app(), _submission("confirmation"))

    body = rd_post.call_args.kwargs["json"]
    assert body["feedbackCategory"] == "CONFIRMATION"
    assert body["label"] == "MANIPULATED"


@pytest.mark.asyncio
async def test_other_without_details_is_rejected_in_the_form(
    slack: dict[str, AsyncMock], rd_post: AsyncMock
) -> None:
    resp = await _send(_app(), _submission("other"))

    assert json.loads(resp.body)["response_action"] == "errors"
    rd_post.assert_not_awaited()
    slack["chat_postEphemeral"].assert_not_awaited()


@pytest.mark.asyncio
async def test_api_error_tells_the_reporter(
    slack: dict[str, AsyncMock], rd_post: AsyncMock
) -> None:
    rd_post.side_effect = RealityDefenderError("Invalid request", "invalid_request")

    await _send(_app(), _submission("false_negative"))

    text = slack["chat_postEphemeral"].call_args.kwargs["text"]
    assert text.startswith(":warning:")
    assert "req-1" in text


@pytest.mark.asyncio
async def test_no_api_key_tells_the_reporter(
    slack: dict[str, AsyncMock], rd_post: AsyncMock
) -> None:
    await _send(_app(shared_key=None), _submission("false_negative"))

    rd_post.assert_not_awaited()
    assert slack["chat_postEphemeral"].call_args.kwargs["text"].startswith(":warning:")
