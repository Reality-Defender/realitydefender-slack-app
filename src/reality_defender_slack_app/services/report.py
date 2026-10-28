"""Branded PDF report for a scan, posted into the result's thread.

Note: This is meant as a bandaid to generate PDF reports in slack until we implement a backend endpoint. Once the backend endpoint exists, this should be replaced.

Built from the full `GET /api/media/users/{requestId}` record (not the SDK's
trimmed DetectionResult) and laid out after the RealScan web app's "Image/Video/
Audio analysis report": a cover with the conclusion and file details, then
Analysis models, Context analysis, Metadata analysis and Known limitations.
Verdict labels (Manipulated / Authentic / ...) appear only in the conclusion;
individual models show a detected / suspicious / not-detected icon.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import aiohttp
from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image, ImageChops, ImageDraw, ImageEnhance

from reality_defender_slack_app.services.formatting import (
    DASHBOARD_BASE,
    MediaOverallStatus,
    is_context_model,
    is_ensemble_model,
    verdict_basis,
)

logger = logging.getLogger(__name__)

TEMPLATE = "report.html.j2"

STATUS_LABELS: dict[str, str] = {
    MediaOverallStatus.FAKE: "Manipulated",
    MediaOverallStatus.MANIPULATED: "Manipulated",
    MediaOverallStatus.SUSPICIOUS: "Suspicious",
    MediaOverallStatus.AUTHENTIC: "Authentic",
    MediaOverallStatus.NOT_APPLICABLE: "Not Applicable",
    MediaOverallStatus.UNABLE_TO_EVALUATE: "Unable to Evaluate",
    MediaOverallStatus.ANALYZING: "Analyzing",
    MediaOverallStatus.DOWNLOADING: "Downloading",
    MediaOverallStatus.DOWNLOAD_FAILED: "Download Failed",
}
# Visual tone per status; maps to the report's colors.
STATUS_TONES: dict[str, str] = {
    MediaOverallStatus.FAKE: "danger",
    MediaOverallStatus.MANIPULATED: "danger",
    MediaOverallStatus.SUSPICIOUS: "warning",
    MediaOverallStatus.AUTHENTIC: "ok",
}
CONCLUSIVE_STATUSES = frozenset(STATUS_TONES)

_MEDIA_NOUNS = {"IMAGE": "image", "VIDEO": "video", "AUDIO": "audio", "TEXT": "text"}
_KIND_TITLES = {
    "IMAGE": "Image analysis report",
    "VIDEO": "Video analysis report",
    "AUDIO": "Audio analysis report",
    "TEXT": "Text analysis report",
}

# Model slug (minus rd-/full-/media suffix) -> technique, as the web app lists them.
# Slugs aren't a stable API contract: unknown ones fall back to the slug's words.
_TECHNIQUES = {
    "cedar": "GANs",
    "elm": "Diffusion",
    "oak": "Face swap",
    "pine": "Visual noise analysis",
    "erie": "Universal",
    "tahoe": "Guided",
    "dynamics": "Dynamics",
    "huron": "Face blending",
    "everest": "Advanced",
    "slim": "Generalizable",
    "llm": "Generative",
}
_SLUG_NOISE = {"rd", "full", "img", "vid", "aud", "txt"}

LIMITATIONS = [
    "Detection reflects the state of technology at the time of analysis; "
    "generation techniques continue to evolve.",
    "Likelihood scores reflect model consensus, not absolute certainty.",
    "Minor, non-deceptive edits (cropping, compression, color correction) are "
    "not flagged as manipulations.",
    "Image analysis is optimized for human-focused imagery and may be less "
    "reliable for non-human scenes.",
    "This report addresses media authenticity only and does not constitute "
    "legal advice.",
]

# Signed evidence URLs expire ~15 minutes after the scan, so they're fetched
# right away; every fetch is best-effort and never blocks the report.
FETCH_TIMEOUT_SECONDS = 20
# Cap embedded images so a 50 MB upload doesn't become a 50 MB PDF.
MAX_IMAGE_EDGE_PX = 1400
MAX_AGGREGATION_BYTES = 5 * 1024 * 1024
# Face-box colors by verdict tone, matching the web app: green for authentic,
# red for flagged.
_BOX_COLORS = {
    "danger": (217, 58, 43),
    "warning": (240, 165, 49),
    "ok": (110, 214, 110),
}
MIN_FACE_CONFIDENCE = 0.5
HEATMAP_COLOR = (217, 58, 43)


@dataclass
class ScanContext:
    """Who asked for the scan and what they submitted, from the Slack side."""

    source_kind: str  # "upload" or "social"
    source_name: str  # original filename or social URL
    requested_at: datetime
    requested_by: str | None = None
    workspace_name: str | None = None
    message_permalink: str | None = None
    sha256: str | None = None


@dataclass
class Fact:
    label: str
    value: str
    mono: bool = False
    href: str | None = None


@dataclass
class Detector:
    slug: str
    status: str
    score: int | None

    @property
    def is_ensemble(self) -> bool:
        return is_ensemble_model(self.slug)

    @property
    def is_context(self) -> bool:
        return is_context_model(self.slug)


@dataclass
class ModelRow:
    name: str
    state: str  # "detected" | "suspicious" | "not_detected"


@dataclass
class ModelTable:
    title: str
    description: str
    rows: list[ModelRow]


@dataclass
class OutcomeRow:
    label: str
    text: str
    state: str


@dataclass
class Source:
    title: str
    source: str
    date: str
    url: str


@dataclass
class Metadata:
    signals: list[str]
    exif: list[Fact]
    c2pa: list[str]
    detected: bool


@dataclass
class Report:
    """Everything the template renders."""

    request_id: str
    title: str
    media_type: str  # IMAGE / VIDEO / AUDIO / TEXT
    status: str
    status_label: str
    is_conclusive: bool
    kind_title: str
    conclusion_label: str
    conclusion_tone: str
    conclusion_text: str
    cover_facts: list[Fact]
    model_tables: list[ModelTable]
    context_rows: list[OutcomeRow]
    sources: list[Source]
    metadata: Metadata | None
    dashboard_url: str | None
    generated_at: datetime
    preview: str | None = None  # data URI
    heatmap: str | None = None  # data URI
    limitations: list[str] = field(default_factory=lambda: list(LIMITATIONS))


# --- public API ------------------------------------------------------------


async def render_report(
    raw: dict[str, Any],
    context: ScanContext,
    *,
    media_id: str | None = None,
    media_bytes: bytes | None = None,
) -> tuple[bytes, str]:
    """Fetch the evidence a report embeds, then render it. Returns (pdf, filename).

    `media_bytes` is the original upload when the bot has it; for images it
    becomes the preview (better than RD's thumbnail, and needs no fetch).
    """
    aggregation, preview, heatmap = await _collect_evidence(raw, media_bytes)
    report = build_report(
        raw,
        context,
        media_id=media_id,
        aggregation=aggregation,
        preview=preview,
        heatmap=heatmap,
    )
    pdf = await asyncio.to_thread(render_pdf, report)
    return pdf, report_filename(report)


def build_report(
    raw: dict[str, Any],
    context: ScanContext,
    *,
    media_id: str | None = None,
    aggregation: dict[str, Any] | None = None,
    preview: str | None = None,
    heatmap: str | None = None,
    generated_at: datetime | None = None,
) -> Report:
    """Shape a raw media result and its Slack context into the report sections."""
    media_type = str(raw.get("mediaType") or "").upper() or "MEDIA"
    noun = _MEDIA_NOUNS.get(media_type, "media")
    summary_block = raw.get("resultsSummary") or {}
    status = overall_status(raw)
    score = _as_score((summary_block.get("metadata") or {}).get("finalScore"))
    is_conclusive = status in CONCLUSIVE_STATUSES
    request_id = str(raw.get("requestId") or "unknown")
    generated_at = generated_at or datetime.now(timezone.utc)

    detectors = _detectors(raw.get("models") or [])
    sources = _sources(raw.get("models") or [])
    metadata = _metadata(aggregation)
    basis = verdict_basis(
        status, raw.get("models") or [], bool(metadata and metadata.detected)
    )

    return Report(
        request_id=request_id,
        title=context.source_name,
        media_type=media_type,
        status=status,
        status_label=STATUS_LABELS.get(status, status.replace("_", " ").title()),
        is_conclusive=is_conclusive,
        kind_title=_KIND_TITLES.get(media_type, "Media analysis report"),
        conclusion_label=_conclusion_label(status),
        conclusion_tone=STATUS_TONES.get(status, "neutral"),
        conclusion_text=_conclusion_text(
            status, noun, score, metadata, basis, summary_block
        ),
        cover_facts=_cover_facts(context, raw, request_id, generated_at),
        model_tables=_model_tables(detectors),
        context_rows=_context_rows(detectors, sources, media_type, noun),
        sources=sources[:6],
        metadata=metadata,
        # Social scans have no media_id; the web app's URL uses the request ID.
        dashboard_url=f"{DASHBOARD_BASE}/{media_id or request_id}",
        generated_at=generated_at,
        preview=preview,
        heatmap=heatmap,
    )


def render_html(report: Report) -> str:
    return (
        _env()
        .get_template(TEMPLATE)
        .render(r=report, waveform=_waveform(report.request_id))
    )


def render_pdf(report: Report) -> bytes:
    """Render the report to PDF bytes.

    WeasyPrint is imported lazily: it needs Pango at runtime, and a missing
    system library should only cost the report, not crash the app on boot.
    """
    from weasyprint import HTML  # type: ignore[import-untyped]

    pdf = HTML(string=render_html(report)).write_pdf()
    if pdf is None:  # write_pdf returns None only when given a target
        raise RuntimeError("WeasyPrint returned no PDF bytes")
    return bytes(pdf)


def report_filename(report: Report) -> str:
    """e.g. 'RD-Report_2026-09-25_a1b2c3d4.pdf'."""
    stamp = report.generated_at.strftime("%Y-%m-%d")
    return f"RD-Report_{stamp}_{report.request_id[:8]}.pdf"


def fmt_time(value: Any) -> str | None:
    """Render an ISO string or datetime as '25 Sep 2026, 14:02 UTC'."""
    if isinstance(value, str) and value:
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return str(value.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC"))
    return None


# --- report sections -------------------------------------------------------


def overall_status(raw: dict[str, Any]) -> str:
    """The scan's verdict: resultsSummary.status, else overallStatus."""
    summary_block = raw.get("resultsSummary") or {}
    return str(
        summary_block.get("status")
        or raw.get("overallStatus")
        or MediaOverallStatus.UNKNOWN
    )


def model_state(status: str) -> str:
    """Individual model outcome: FAKE -> detected, SUSPICIOUS -> suspicious."""
    if status in (MediaOverallStatus.FAKE, MediaOverallStatus.MANIPULATED):
        return "detected"
    if status == MediaOverallStatus.SUSPICIOUS:
        return "suspicious"
    return "not_detected"


def _as_score(value: Any) -> int | None:
    """Normalize a 0-100 score; negative sentinels (e.g. -1) mean 'no score'."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return int(round(value))


def _technique(slug: str) -> str:
    parts = [p for p in slug.split("-") if p and p not in _SLUG_NOISE]
    key = "-".join(parts)
    return _TECHNIQUES.get(key) or " ".join(p.capitalize() for p in parts) or slug


def _detectors(models: list[dict[str, Any]]) -> list[Detector]:
    """Models that reached a verdict, strongest signal first."""
    rows = []
    for model in models:
        status = str(model.get("status") or MediaOverallStatus.UNKNOWN)
        if status not in CONCLUSIVE_STATUSES:
            continue
        score = _as_score(model.get("finalScore"))
        if score is None:
            score = _as_score(model.get("normalizedPredictionNumber"))
        rows.append(Detector(str(model.get("name") or "unknown"), status, score))
    rows.sort(key=lambda d: -(d.score or 0))
    return rows


def _sources(models: list[dict[str, Any]]) -> list[Source]:
    """Reverse image search matches the context-aware model found online."""
    matches = []
    for model in models:
        data = model.get("data")
        if not isinstance(data, dict):
            continue
        for src in data.get("sources") or []:
            if isinstance(src, dict) and src.get("url"):
                matches.append(
                    Source(
                        title=str(src.get("title") or src["url"]),
                        source=str(src.get("source") or ""),
                        date=str(src.get("date") or ""),
                        url=str(src["url"]),
                    )
                )
    return matches


def _metadata(aggregation: dict[str, Any] | None) -> Metadata | None:
    """Metadata/provenance checks from aggregation.json's `provenance` block."""
    prov = aggregation.get("provenance") if isinstance(aggregation, dict) else None
    if not isinstance(prov, dict):
        return None
    signals = []
    for reason in prov.get("reasons") or []:
        if isinstance(reason, dict):
            text = reason.get("signal") or reason.get("message") or reason.get("reason")
        else:
            text = reason
        if text:
            signals.append(str(text))
    exif_tags = prov.get("exif_tags")
    exif = (
        [Fact(str(k), str(v)) for k, v in list(exif_tags.items())[:8] if v]
        if isinstance(exif_tags, dict)
        else []
    )
    return Metadata(
        signals=signals,
        exif=exif,
        c2pa=[str(i) for i in prov.get("c2pa_indicators") or [] if i],
        detected=prov.get("is_generated") is True or bool(signals),
    )


def _conclusion_label(status: str) -> str:
    if status in CONCLUSIVE_STATUSES:
        return STATUS_LABELS[status]
    if status == MediaOverallStatus.UNABLE_TO_EVALUATE:
        return "Unable to evaluate"
    return "Inconclusive"


def _article(n: int) -> str:
    """'an 8%' / 'an 80%' / 'an 18%' / 'a 92%' — spoken-number article."""
    vowel_sound = str(n).startswith("8") or n in (11, 18)
    return "an" if vowel_sound else "a"


def _conclusion_text(
    status: str,
    noun: str,
    score: int | None,
    metadata: Metadata | None,
    basis: str,
    summary_block: dict[str, Any],
) -> str:
    if basis == "context":
        return (
            f"Context surrounding this {noun} indicates that it's likely to have been "
            f"manipulated. None of the detection models found signs of manipulation "
            f"in the {noun} itself."
        )
    metadata_text = (
        "The file metadata contains signals indicating this file was "
        "generated or altered using AI."
    )
    if basis == "metadata":
        return metadata_text
    if basis == "context_metadata":
        return (
            f"The file metadata and the context surrounding this {noun} indicate "
            "that it's likely to have been generated or altered using AI."
        )
    if status in CONCLUSIVE_STATUSES and score is not None:
        return (
            f"There's {_article(score)} {score}% likelihood that this "
            f"{noun} has been manipulated. Scores from multiple models have been "
            "combined to create this conclusion."
        )
    if status in CONCLUSIVE_STATUSES and metadata and metadata.detected:
        return metadata_text
    return _summary(status, noun, score, summary_block)


def _summary(
    status: str, noun: str, score: int | None, summary_block: dict[str, Any]
) -> str:
    """One plain-language sentence a reporter can act on."""
    if status in (MediaOverallStatus.FAKE, MediaOverallStatus.MANIPULATED):
        strength = "strong signs" if (score or 0) >= 90 else "signs"
        return (
            f"Our analysis found {strength} that this {noun} was created or "
            "altered using AI."
        )
    if status == MediaOverallStatus.SUSPICIOUS:
        return (
            f"Our analysis found some signs that this {noun} may have been altered "
            "using AI, but the result isn't conclusive."
        )
    if status == MediaOverallStatus.AUTHENTIC:
        return (
            f"Our analysis found no signs that this {noun} was created or altered "
            "using AI."
        )
    if status == MediaOverallStatus.NOT_APPLICABLE:
        reasons = []
        for reason in (summary_block.get("metadata") or {}).get("reasons") or []:
            if isinstance(reason, dict):
                reason = (
                    reason.get("explanation")
                    or reason.get("message")
                    or reason.get("name")
                )
            if reason:
                reasons.append(str(reason).rstrip("."))
        if reasons:
            return f"We couldn't check this {noun}: {'; '.join(reasons)}."
        return f"We couldn't check this {noun}."
    if status == MediaOverallStatus.DOWNLOAD_FAILED:
        return "We couldn't download the media from this link."
    if status == MediaOverallStatus.UNABLE_TO_EVALUATE:
        return (
            f"We couldn't finish checking this {noun} because of a technical "
            "problem on our side."
        )
    label = STATUS_LABELS.get(status, status.replace("_", " ").title())
    return f"This check is still in progress ({label.lower()})."


def _cover_facts(
    ctx: ScanContext, raw: dict[str, Any], request_id: str, generated_at: datetime
) -> list[Fact]:
    facts = []
    if ctx.workspace_name:
        facts.append(Fact("Prepared for", ctx.workspace_name))
    if ctx.source_kind == "social":
        facts.append(Fact("Link", ctx.source_name, href=ctx.source_name))
    else:
        facts.append(Fact("File name", ctx.source_name))
    if ctx.requested_by:
        facts.append(Fact("Submitted by", ctx.requested_by))
    submitted = fmt_time(raw.get("uploadedDate")) or fmt_time(ctx.requested_at)
    if submitted:
        facts.append(Fact("Media submitted", submitted))
    facts.append(Fact("Report created", fmt_time(generated_at) or ""))
    facts.append(Fact("Report ID", request_id, mono=True))
    if ctx.sha256:
        facts.append(Fact("File hash", f"SHA-256 {ctx.sha256}", mono=True))
    if ctx.message_permalink:
        facts.append(
            Fact("Slack", "Open the original message", href=ctx.message_permalink)
        )
    return facts


def _model_tables(detectors: list[Detector]) -> list[ModelTable]:
    full: list[ModelRow] = []
    face: list[ModelRow] = []
    audio: list[ModelRow] = []
    text: list[ModelRow] = []
    for d in detectors:
        if d.is_ensemble or d.is_context:
            continue
        row = ModelRow(_technique(d.slug), model_state(d.status))
        if d.slug.startswith("rd-full-"):
            full.append(row)
        elif d.slug.endswith("-aud") or "-aud-" in d.slug:
            audio.append(row)
        elif d.slug.endswith("-txt"):
            text.append(row)
        else:
            face.append(row)

    tables = []
    if full:
        tables.append(
            ModelTable(
                "Full frame models",
                "Analysis of the entire frame to detect manipulation signals "
                "outside of faces, including backgrounds, textures and scene "
                "composition.",
                full,
            )
        )
    if face:
        tables.append(
            ModelTable(
                "Face models",
                "AI models that analyze facial regions for artifacts associated "
                "with AI generation, face swaps and other facial manipulation.",
                face,
            )
        )
    if audio:
        tables.append(
            ModelTable(
                "Audio models",
                "AI models that listen for signs of synthetic or cloned speech.",
                audio,
            )
        )
    if text:
        tables.append(
            ModelTable(
                "Text models",
                "AI models that look for signs the text was written by AI.",
                text,
            )
        )
    return tables


def _context_rows(
    detectors: list[Detector], sources: list[Source], media_type: str, noun: str
) -> list[OutcomeRow]:
    context = next((d for d in detectors if d.is_context), None)
    if context is None:
        return []
    state = model_state(context.status)
    general = {
        "detected": "Context surrounding this media indicates that it's likely to "
        "have been manipulated.",
        "suspicious": "Context surrounding this media raises some concerns that it "
        "may have been manipulated.",
        "not_detected": "No context to suggest this media has been manipulated.",
    }[state]
    rows = [OutcomeRow("General context", general, state)]
    if media_type == "IMAGE" or sources:
        if not sources:
            text = f"No other instances of this {noun} found online."
            search_state = "not_detected"
        elif state != "not_detected":
            text = (
                f"Other instances of this {noun} were found online. The "
                "surrounding content suggests it may have been manipulated."
            )
            search_state = state
        else:
            text = (
                f"Other instances of this {noun} were found online. No "
                "surrounding context to suggest it has been manipulated."
            )
            search_state = "not_detected"
        rows.append(OutcomeRow("Reverse image search", text, search_state))
    return rows


# --- evidence --------------------------------------------------------------


def usable_heatmap_urls(raw: dict[str, Any]) -> list[str]:
    """Heatmaps worth showing: image scans, non-ensemble models flagged FAKE.

    The API returns heatmap URLs for every model, but only these point at real
    files (context-aware models list one too, but it 404s).
    """
    heatmaps = raw.get("heatmaps")
    if str(raw.get("mediaType") or "").upper() != "IMAGE" or not isinstance(
        heatmaps, dict
    ):
        return []
    flagged = {
        m.get("name")
        for m in raw.get("models") or []
        if m.get("status") == MediaOverallStatus.FAKE
        and "ensemble" not in str(m.get("name", ""))
        and not str(m.get("name", "")).startswith("rd-context-")
    }
    return [
        url
        for name, url in heatmaps.items()
        if name in flagged and isinstance(url, str) and url
    ]


def face_boxes(
    aggregation: dict[str, Any] | None,
) -> tuple[list[tuple[float, float, float, float]], Any]:
    """Face rectangles (x1, y1, x2, y2) from aggregation.json, plus its image size.

    Each bbox entry carries `faceboxes: [x1, y1, x2, y2, confidence]` in the
    analyzed image's pixel space (`aggregation["image"]` gives that size).
    """
    if not isinstance(aggregation, dict):
        return [], None
    boxes = []
    for entry in aggregation.get("bboxes") or []:
        fb = entry.get("faceboxes") if isinstance(entry, dict) else None
        if not isinstance(fb, list) or len(fb) < 4:
            continue
        conf = fb[4] if len(fb) > 4 and isinstance(fb[4], (int, float)) else 1.0
        if conf < MIN_FACE_CONFIDENCE:
            continue
        try:
            boxes.append((float(fb[0]), float(fb[1]), float(fb[2]), float(fb[3])))
        except (TypeError, ValueError):
            continue
    return boxes, aggregation.get("image")


def heatmap_overlay(base_bytes: bytes, heatmaps: list[bytes]) -> str | None:
    """Blend RD heatmaps onto the original image as one red overlay.

    RD heatmaps are white 'LA' images whose alpha channel marks how much each
    region contributed; on their own they look blank. Their alphas are merged
    (strongest signal wins) and painted over a slightly dimmed original.
    """
    try:
        with Image.open(io.BytesIO(base_bytes)) as src:
            base = src.convert("RGB")
        mask: Image.Image | None = None
        for body in heatmaps:
            with Image.open(io.BytesIO(body)) as hm:
                alpha = hm.convert("RGBA").getchannel("A").resize(base.size)
            mask = alpha if mask is None else ImageChops.lighter(mask, alpha)
        if mask is None:
            return None
        base = ImageEnhance.Brightness(base).enhance(0.8)
        color = Image.new("RGB", base.size, HEATMAP_COLOR)
        mask = mask.point(lambda v: int(v * 0.75))
        out = io.BytesIO()
        Image.composite(color, base, mask).save(out, format="PNG")
    except Exception:
        logger.warning("Could not build heatmap overlay", exc_info=True)
        return None
    return to_data_uri(out.getvalue())


def to_data_uri(
    image_bytes: bytes,
    *,
    boxes: list[tuple[float, float, float, float]] | None = None,
    source_size: Any = None,
    box_status: str | None = None,
) -> str | None:
    """Downscale and re-encode an image as an embeddable JPEG/PNG data URI,
    optionally outlining detected faces."""
    try:
        with Image.open(io.BytesIO(image_bytes)) as opened:
            opened.load()
            img: Image.Image = opened
            if boxes:
                color = _BOX_COLORS[STATUS_TONES.get(box_status or "", "ok")]
                img = _draw_boxes(img, boxes, source_size, color)
            has_alpha = img.mode in ("RGBA", "LA") or "transparency" in img.info
            img.thumbnail((MAX_IMAGE_EDGE_PX, MAX_IMAGE_EDGE_PX))
            out = io.BytesIO()
            if has_alpha:
                img.convert("RGBA").save(out, format="PNG", optimize=True)
                mime = "image/png"
            else:
                img.convert("RGB").save(out, format="JPEG", quality=85)
                mime = "image/jpeg"
    except Exception:
        logger.warning("Could not decode image for report embedding", exc_info=True)
        return None
    return f"data:{mime};base64,{base64.b64encode(out.getvalue()).decode('ascii')}"


def _draw_boxes(
    img: Image.Image,
    boxes: list[tuple[float, float, float, float]],
    source_size: Any,
    color: tuple[int, int, int],
) -> Image.Image:
    sx = sy = 1.0
    if isinstance(source_size, dict):
        w, h = source_size.get("width"), source_size.get("height")
        if isinstance(w, (int, float)) and isinstance(h, (int, float)) and w and h:
            sx, sy = img.width / w, img.height / h
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)
    width = max(2, round(min(img.size) / 250))
    for x1, y1, x2, y2 in boxes:
        rect = (
            max(0, x1 * sx),
            max(0, y1 * sy),
            min(img.width - 1, x2 * sx),
            min(img.height - 1, y2 * sy),
        )
        draw.rectangle(rect, outline=color, width=width)
    return img


async def _get_bytes(session: aiohttp.ClientSession, url: str) -> bytes | None:
    try:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return await resp.read()
    except Exception:
        logger.warning("Evidence fetch failed", exc_info=True)
        return None


async def _collect_evidence(
    raw: dict[str, Any], media_bytes: bytes | None
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Download what the report embeds: (aggregation.json, preview, heatmap)."""
    media_type = str(raw.get("mediaType") or "").upper()

    async def _none() -> None:
        return None

    async def _given() -> bytes | None:
        return media_bytes

    # Signed S3 URLs carry their own auth, so no RD credentials are sent.
    timeout = aiohttp.ClientTimeout(total=FETCH_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        use_original = bool(media_bytes) and media_type == "IMAGE"
        if use_original:
            preview_src = _given()
        elif raw.get("thumbnail"):
            preview_src = _get_bytes(session, raw["thumbnail"])
        else:
            preview_src = _none()
        agg_url = raw.get("modelMetadataUrl")
        preview_bytes, agg_body, *heatmap_bodies = await asyncio.gather(
            preview_src,
            _get_bytes(session, agg_url) if agg_url else _none(),
            *(_get_bytes(session, url) for url in usable_heatmap_urls(raw)),
        )

    aggregation = None
    if agg_body and len(agg_body) <= MAX_AGGREGATION_BYTES:
        try:
            parsed = json.loads(agg_body)
            aggregation = parsed if isinstance(parsed, dict) else None
        except ValueError:
            pass

    preview = heatmap = None
    bodies = [b for b in heatmap_bodies if b]
    if bodies and preview_bytes and media_type == "IMAGE":
        heatmap = await asyncio.to_thread(heatmap_overlay, preview_bytes, bodies)
    if preview_bytes:
        # Face boxes are in the analyzed image's pixels; only draw them on the
        # original image, where that mapping holds (not on RD's thumbnail).
        boxes, size = face_boxes(aggregation) if use_original else ([], None)
        preview = await asyncio.to_thread(
            to_data_uri,
            preview_bytes,
            boxes=boxes,
            source_size=size,
            box_status=overall_status(raw),
        )
    return aggregation, preview, heatmap


# --- rendering -------------------------------------------------------------


def _waveform(seed: str, n: int = 90) -> list[int]:
    """Decorative, deterministic waveform for audio covers (no real samples)."""
    rng = random.Random(seed)
    heights = []
    for i in range(n):
        envelope = 0.35 + 0.65 * abs(((i * 7) % 40) - 20) / 20
        heights.append(max(3, int(rng.uniform(0.3, 1.0) * envelope * 56)))
    return heights


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(Path(__file__).parent)),
        autoescape=select_autoescape(["j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
