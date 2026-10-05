"""'Report an issue' on a result: false positive/negative, confirmation, or a question.

The button under each result opens a short form. Submitting it sends the
report to Reality Defender with the SDK's user-feedback API (tagged with the
scan's request ID and the Slack reporter), then shows the reporter a private
confirmation in the thread.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from slack_bolt.app.async_app import AsyncApp

from reality_defender_slack_app.deps import Deps
from reality_defender_slack_app.services.formatting import REPORT_ACTION_ID
from reality_defender_slack_app.services.keys import resolve_api_key
from reality_defender_slack_app.views import REPORT_VIEW_ID, open_report_issue_modal

logger = logging.getLogger(__name__)

SUPPORT_EMAIL = "support@realitydefender.com"

# Form choice -> (feedback category, label). A confirmation's label follows the
# verdict the reporter agreed with.
CHOICES = {
    "false_positive": ("FALSE_POSITIVE", "REAL"),
    "false_negative": ("FALSE_NEGATIVE", "MANIPULATED"),
    "confirmation": ("CONFIRMATION", None),
    "other": ("OTHER", "UNKNOWN"),
}

CONFIRMATION_TEXT = (
    ":white_check_mark: Thanks, your report was sent to Reality Defender "
    "(Request ID `{request_id}`). For any questions about this result, email "
    f"{SUPPORT_EMAIL}."
)
FAILURE_TEXT = (
    ":warning: We couldn't send your report. Please email "
    f"{SUPPORT_EMAIL} and include Request ID `{{request_id}}`."
)


def _confirmation_label(status: str) -> str:
    if status in ("FAKE", "MANIPULATED", "SUSPICIOUS"):
        return "MANIPULATED"
    if status == "AUTHENTIC":
        return "REAL"
    return "UNKNOWN"


def _form_values(view: dict[str, Any]) -> tuple[str | None, str]:
    values = view.get("state", {}).get("values", {})
    selected = values.get("issue", {}).get("choice", {}).get("selected_option") or {}
    details = values.get("details", {}).get("text", {}).get("value") or ""
    return selected.get("value"), details.strip()


def register_feedback_handlers(app: AsyncApp, deps: Deps) -> None:
    @app.action(REPORT_ACTION_ID)
    async def open_report_form(ack: Any, body: Any, client: Any) -> None:
        await ack()
        try:
            value = json.loads(body["actions"][0]["value"])
        except (KeyError, IndexError, ValueError):
            logger.warning("Report button without a valid payload")
            return
        message = body.get("message") or {}
        metadata = {
            "request_id": value.get("request_id", ""),
            "status": value.get("status", ""),
            "channel_id": (body.get("channel") or {}).get("id", ""),
            "thread_ts": message.get("thread_ts") or message.get("ts", ""),
        }
        await open_report_issue_modal(client, body["trigger_id"], metadata)

    @app.view(REPORT_VIEW_ID)
    async def submit_report(
        ack: Any, body: Any, view: Any, client: Any, context: Any
    ) -> None:
        choice, details = _form_values(view)
        if choice == "other" and not details:
            await ack(
                response_action="errors",
                errors={"details": "Tell us a bit more so we can help."},
            )
            return
        await ack()

        metadata = json.loads(view.get("private_metadata") or "{}")
        request_id = metadata.get("request_id", "")
        user = body.get("user") or {}
        category, label = CHOICES.get(choice or "other", CHOICES["other"])
        label = label or _confirmation_label(metadata.get("status", ""))
        reporter = user.get("name") or user.get("id") or "unknown"
        comment = f"Reported from Slack by {reporter} ({user.get('id', '')})."
        if details:
            comment += f"\n{details}"

        sent = False
        api_key = await resolve_api_key(
            deps.key_store, context.get("team_id"), deps.settings
        )
        if api_key and request_id:
            try:
                await deps.rd_client.submit_feedback(
                    api_key,
                    request_id,
                    label=label,  # type: ignore[arg-type]
                    category=category,  # type: ignore[arg-type]
                    comment=comment,
                )
                sent = True
            except Exception:
                logger.exception("Feedback submission failed for %s", request_id)
        else:
            logger.warning("No API key or request ID for feedback on %r", request_id)

        text = (CONFIRMATION_TEXT if sent else FAILURE_TEXT).format(
            request_id=request_id
        )
        try:
            await client.chat_postEphemeral(
                channel=metadata.get("channel_id"),
                user=user.get("id"),
                thread_ts=metadata.get("thread_ts") or None,
                text=text,
            )
        except Exception:
            logger.exception("Failed to post report confirmation")
