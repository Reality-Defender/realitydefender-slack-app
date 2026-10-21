from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

DASHBOARD_BASE = "https://app.realitydefender.ai/media"

# Statuses RD reports for a scan and for each model. Raw media records say FAKE;
# the SDK's DetectionResult renames it MANIPULATED.
FAKE = "FAKE"
MANIPULATED = "MANIPULATED"
SUSPICIOUS = "SUSPICIOUS"
AUTHENTIC = "AUTHENTIC"
NOT_APPLICABLE = "NOT_APPLICABLE"
UNABLE_TO_EVALUATE = "UNABLE_TO_EVALUATE"
ANALYZING = "ANALYZING"
DOWNLOADING = "DOWNLOADING"
DOWNLOAD_FAILED = "DOWNLOAD_FAILED"
# Ours, not RD's: used when a result carries no status at all.
UNKNOWN = "UNKNOWN"

FLAGGED_STATUSES = frozenset({FAKE, MANIPULATED, SUSPICIOUS})

STATUS_EMOJI = {
    AUTHENTIC: ":white_check_mark:",
    MANIPULATED: ":warning:",
    UNKNOWN: ":grey_question:",
}


def format_result(result: Mapping[str, Any], label: str, media_id: str | None = None) -> str:
    status = result.get("status", UNKNOWN)
    score = result.get("score")
    emoji = STATUS_EMOJI.get(status, ":grey_question:")

    # Only a verdict the detection models reached has a score that's a likelihood.
    basis = verdict_basis(status, result.get("models") or [])
    show_score = score is not None and basis == "models"
    confidence = f"`{score:.0%}` confidence of manipulation" if show_score else ""
    lines = [f"{emoji} *{status}*  {confidence}\nSource: `{label}`"]

    if media_id:
        lines.append(f"\n<{DASHBOARD_BASE}/{media_id}|View full report in Reality Defender →>")

    return "\n".join(lines)


def is_context_model(name: str) -> bool:
    return name.startswith("rd-context-")


def is_ensemble_model(name: str) -> bool:
    return name.endswith("ensemble")


def verdict_basis(
    status: str, models: Iterable[Mapping[str, Any]], metadata_detected: bool = False
) -> str:
    """What a flagged verdict rests on: "models", "context", "metadata" or both.

    RD's overall score for a verdict driven only by context-aware or metadata
    analysis is that one signal's score (e.g. the context model's 82 while every
    detection model scored 1-4), so it isn't shown as a likelihood. Shared by the
    Slack message and the PDF report so the two always agree.
    """
    if status not in FLAGGED_STATUSES:
        return "models"
    flagged = [
        str(m.get("name", "")) for m in models if m.get("status") in FLAGGED_STATUSES
    ]
    if any(not is_context_model(n) and not is_ensemble_model(n) for n in flagged):
        return "models"
    context = any(is_context_model(n) for n in flagged)
    if context and metadata_detected:
        return "context_metadata"
    if context:
        return "context"
    if metadata_detected:
        return "metadata"
    return "models"
