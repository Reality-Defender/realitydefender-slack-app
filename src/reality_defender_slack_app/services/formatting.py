from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

DASHBOARD_BASE = "https://app.realitydefender.ai/media"

# Action ID of the "Report an issue" button (handled in handlers/feedback.py).
REPORT_ACTION_ID = "report_issue"

_FLAGGED = {"MANIPULATED", "SUSPICIOUS"}

STATUS_EMOJI = {
    "AUTHENTIC": ":white_check_mark:",
    "MANIPULATED": ":warning:",
    "UNKNOWN": ":grey_question:",
}


def format_result(result: Mapping[str, Any], label: str, media_id: str | None = None) -> str:
    status = result.get("status", "UNKNOWN")
    score = result.get("score")
    emoji = STATUS_EMOJI.get(status, ":grey_question:")

    # A context-only verdict's score is that one signal's, not a likelihood.
    show_score = score is not None and not _context_only(result)
    confidence = f"`{score:.0%}` confidence of manipulation" if show_score else ""
    lines = [f"{emoji} *{status}*  {confidence}\nSource: `{label}`"]

    if media_id:
        lines.append(f"\n<{DASHBOARD_BASE}/{media_id}|View full report in Reality Defender →>")

    return "\n".join(lines)


def _context_only(result: Mapping[str, Any]) -> bool:
    """Flagged only by context-aware analysis: no detection model flagged it."""
    models = result.get("models") or []
    context = any(
        str(m.get("name", "")).startswith("rd-context-") and m.get("status") in _FLAGGED
        for m in models
    )
    detection = any(
        m.get("status") in _FLAGGED
        and not str(m.get("name", "")).startswith("rd-context-")
        and not str(m.get("name", "")).endswith("ensemble")
        for m in models
    )
    return context and not detection


def result_blocks(text: str, request_id: str, status: str) -> list[dict[str, Any]]:
    """The result text as-is, with a "Report an issue" button under it."""
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "action_id": REPORT_ACTION_ID,
                    "text": {"type": "plain_text", "text": "Report an issue"},
                    "value": json.dumps({"request_id": request_id, "status": status}),
                }
            ],
        },
    ]
