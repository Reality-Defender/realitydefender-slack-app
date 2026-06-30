from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DASHBOARD_BASE = "https://app.realitydefender.ai/media"

STATUS_EMOJI = {
    "AUTHENTIC": ":white_check_mark:",
    "MANIPULATED": ":warning:",
    "UNKNOWN": ":grey_question:",
}


def format_result(result: Mapping[str, Any], label: str, media_id: str | None = None) -> str:
    status = result.get("status", "UNKNOWN")
    score = result.get("score")
    emoji = STATUS_EMOJI.get(status, ":grey_question:")

    confidence = f"`{score:.0%}` confidence of manipulation" if score is not None else ""
    lines = [f"{emoji} *{status}*  {confidence}\nSource: `{label}`"]

    if media_id:
        lines.append(f"\n<{DASHBOARD_BASE}/{media_id}|View full report in Reality Defender →>")

    return "\n".join(lines)
