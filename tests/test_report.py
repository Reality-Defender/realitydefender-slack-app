from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

from reality_defender_slack_app.services import analysis, report
from reality_defender_slack_app.services.formatting import format_result
from reality_defender_slack_app.services.reality_defender import Analysis

NOW = datetime(2026, 9, 27, 21, 11, tzinfo=timezone.utc)


def _raw(status: str = "AUTHENTIC", **models: str) -> dict[str, Any]:
    return {
        "requestId": "4d79ae19-26c6-431d-b1a9-66f9dabfd078",
        "mediaType": "IMAGE",
        "uploadedDate": "2026-09-27T21:11:00Z",
        "resultsSummary": {"status": status, "metadata": {"finalScore": 4}},
        "models": [
            {"name": name, "status": s, "finalScore": i}
            for i, (name, s) in enumerate(models.items())
        ],
    }


def _ctx(**extra: Any) -> report.ScanContext:
    return report.ScanContext("upload", "photo.webp", NOW, **extra)


def test_model_tables_group_and_name_techniques() -> None:
    raw = _raw(
        **{
            "rd-full-pine-img": "AUTHENTIC",
            "rd-elm-img": "FAKE",
            "rd-oak-img": "SUSPICIOUS",
            "rd-img-ensemble": "AUTHENTIC",
            "rd-context-img": "AUTHENTIC",
            "rd-cedar-vid": "NOT_APPLICABLE",
        }
    )
    r = report.build_report(raw, _ctx(), generated_at=NOW)

    tables = {t.title: [(m.name, m.state) for m in t.rows] for t in r.model_tables}
    # Strongest signal first; ensemble, context and N/A models aren't listed.
    assert tables == {
        "Full frame models": [("Visual noise analysis", "not_detected")],
        "Face models": [("Face swap", "suspicious"), ("Diffusion", "detected")],
    }
    assert r.conclusion_text.startswith("There's a 4% likelihood that this image")


def test_context_only_verdict_hides_the_score() -> None:
    raw = _raw("FAKE", **{"rd-elm-img": "AUTHENTIC", "rd-context-img": "FAKE"})
    raw["models"][1]["data"] = {
        "sources": [{"url": "https://x.com/p/1", "title": "Fake photo", "source": "X"}]
    }
    r = report.build_report(raw, _ctx(), generated_at=NOW)

    assert r.conclusion_label == "Manipulated"
    assert r.conclusion_text.startswith("Context surrounding this image indicates")
    assert [(o.label, o.state) for o in r.context_rows] == [
        ("General context", "detected"),
        ("Reverse image search", "detected"),
    ]
    assert [s.source for s in r.sources] == ["X"]


def test_failed_scan_is_inconclusive_with_explanation() -> None:
    raw = _raw("DOWNLOAD_FAILED")
    r = report.build_report(raw, _ctx(), generated_at=NOW)

    assert r.conclusion_label == "Inconclusive"
    assert r.conclusion_tone == "neutral"
    assert r.conclusion_text == "We couldn't download the media from this link."
    assert r.model_tables == []


def test_cover_facts_and_filename() -> None:
    ctx = _ctx(
        requested_by="Emily Essig",
        workspace_name="Reality Defender",
        sha256="ab" * 32,
        message_permalink="https://acme.slack.com/archives/C1/p1",
    )
    r = report.build_report(_raw(), ctx, media_id="m-1", generated_at=NOW)

    assert [f.label for f in r.cover_facts] == [
        "Prepared for",
        "File name",
        "Submitted by",
        "Media submitted",
        "Report created",
        "Report ID",
        "File hash",
        "Slack",
    ]
    assert r.dashboard_url == "https://app.realitydefender.ai/media/m-1"
    assert report.report_filename(r) == "RD-Report_photo_2026-09-27_4d79ae19.pdf"


def test_metadata_signals_from_aggregation() -> None:
    aggregation = {
        "provenance": {
            "reasons": [{"signal": "Software: Midjourney"}],
            "exif_tags": {"Software": "Midjourney"},
            "c2pa_indicators": ["c2pa.created"],
        }
    }
    r = report.build_report(_raw(), _ctx(), aggregation=aggregation, generated_at=NOW)

    assert r.metadata is not None
    assert r.metadata.detected
    assert r.metadata.signals == ["Software: Midjourney"]
    assert r.metadata.c2pa == ["c2pa.created"]


def test_render_pdf() -> None:
    raw = _raw(**{"rd-full-pine-img": "AUTHENTIC", "rd-context-img": "AUTHENTIC"})
    r = report.build_report(raw, _ctx(requested_by="Ünïcödé 名前"), generated_at=NOW)

    html = report.render_html(r)
    assert "Image analysis report" in html
    assert "Ünïcödé 名前" in html
    assert report.render_pdf(r).startswith(b"%PDF")


def test_slack_result_hides_score_when_only_context_flagged() -> None:
    flagged_by_context = {
        "status": "MANIPULATED",
        "score": 0.82,
        "models": [
            {"name": "rd-elm-img", "status": "AUTHENTIC"},
            {"name": "rd-context-img", "status": "MANIPULATED"},
        ],
    }
    assert "confidence" not in format_result(flagged_by_context, "photo.webp")

    flagged_by_model = {
        **flagged_by_context,
        "models": [{"name": "rd-elm-img", "status": "MANIPULATED"}],
    }
    assert "`82%` confidence" in format_result(flagged_by_model, "photo.webp")


@pytest.mark.asyncio
async def test_result_posts_then_uploads_pdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    render = AsyncMock(return_value=(b"%PDF", "RD-Report_a.pdf"))
    monkeypatch.setattr(analysis, "render_report", render)
    client = AsyncMock()
    context = _ctx()
    result = {"status": "AUTHENTIC", "score": 0.04, "models": []}

    await analysis._post_result(
        client=client,
        channel_id="C1",
        thread_ts="1.1",
        reply="RESULT",
        analysis=Analysis(result, "req-1", "m-1", {"requestId": "req-1"}),  # type: ignore[arg-type]
        context=context,
    )

    posted = client.chat_postMessage.call_args.kwargs
    assert posted["text"] == "RESULT"
    assert render.call_args.args[1] is context
    upload = client.files_upload_v2.call_args.kwargs
    assert upload["thread_ts"] == "1.1"
    assert upload["file"] == b"%PDF"
    assert upload["filename"] == "RD-Report_a.pdf"


@pytest.mark.asyncio
async def test_report_failure_keeps_the_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        analysis, "render_report", AsyncMock(side_effect=OSError("pango"))
    )
    client = AsyncMock()

    await analysis._post_result(
        client=client,
        channel_id="C1",
        thread_ts="1.1",
        reply="RESULT",
        analysis=Analysis({"status": "AUTHENTIC"}, "req-1", None, {}),  # type: ignore[typeddict-item]
        context=_ctx(),
    )

    client.chat_postMessage.assert_awaited_once()
    client.files_upload_v2.assert_not_awaited()
