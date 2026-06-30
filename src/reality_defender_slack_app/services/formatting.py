from __future__ import annotations

from collections.abc import Mapping
from typing import Any

DASHBOARD_BASE = "https://app.realitydefender.ai/media"

STATUS_EMOJI = {
    "AUTHENTIC": ":white_check_mark:",
    "MANIPULATED": ":warning:",
    "UNKNOWN": ":grey_question:",
}

# Keyword-based model groupings. Model names from the RD API are matched
# case-insensitively against these keywords. Adjust as you observe real names.
MODEL_GROUPS = {
    "Visual Analysis": ["face", "visual", "image", "video", "deepfake", "gan", "diffusion"],
    "Audio Analysis": ["audio", "voice", "speech", "sound"],
    "Provenance & Metadata": ["metadata", "exif", "c2pa", "provenance"],
}


def _group_models(models: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {group: [] for group in MODEL_GROUPS}
    grouped["Model Breakdown"] = []

    for model in models:
        name_lower = model.get("name", "").lower()
        matched = False
        for group, keywords in MODEL_GROUPS.items():
            if any(kw in name_lower for kw in keywords):
                grouped[group].append(model)
                matched = True
                break
        if not matched:
            grouped["Model Breakdown"].append(model)

    return {k: v for k, v in grouped.items() if v}  # drop empty groups


def format_result(result: Mapping[str, Any], label: str, media_id: str | None = None) -> str:
    status = result.get("status", "UNKNOWN")
    score = result.get("score")
    emoji = STATUS_EMOJI.get(status, ":grey_question:")

    confidence = f"`{score:.0%}` confidence of manipulation" if score is not None else ""
    lines = [f"{emoji} *{status}*  {confidence}\nSource: `{label}`"]

    models = result.get("models") or []
    if models:
        grouped = _group_models(models)
        lines.append("")
        for group_name, group_models in grouped.items():
            lines.append(f"*{group_name}*")
            for m in group_models:
                m_score = f"`{m['score']:.0%}`" if m.get("score") is not None else "—"
                # Drop any models that aren't used
                if m["status"] != "ANALYZING":
                    lines.append(f"  • {m['name']}: {m['status']}  {m_score}")

    if media_id:
        lines.append(f"\n<{DASHBOARD_BASE}/{media_id}|View full report in Reality Defender →>")

    return "\n".join(lines)
