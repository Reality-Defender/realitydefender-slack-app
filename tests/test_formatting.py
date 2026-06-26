from reality_defender_slack_app.services.formatting import _group_models, format_result


def test_format_result_manipulated_with_models_and_media_id() -> None:
    result = {
        "status": "MANIPULATED",
        "score": 0.92,
        "models": [
            {"name": "face-detector", "status": "MANIPULATED", "score": 0.95},
            {"name": "voice-clone", "status": "AUTHENTIC", "score": 0.10},
        ],
    }

    out = format_result(result, "photo.jpg", media_id="abc123")

    assert ":warning:" in out
    assert "*MANIPULATED*" in out
    assert "92%" in out
    assert "Source: `photo.jpg`" in out
    assert "*Visual Analysis*" in out
    assert "*Audio Analysis*" in out
    assert "abc123" in out


def test_format_result_authentic_minimal() -> None:
    out = format_result({"status": "AUTHENTIC", "score": 0.01}, "clip.mp4")

    assert ":white_check_mark:" in out
    assert "*AUTHENTIC*" in out
    assert "View full report" not in out
    assert "Model Breakdown" not in out


def test_format_result_unknown_status_falls_back() -> None:
    out = format_result({}, "thing")

    assert ":grey_question:" in out
    assert "*UNKNOWN*" in out


def test_group_models_buckets_by_keyword() -> None:
    models = [
        {"name": "image-gan", "status": "X"},
        {"name": "speech-synth", "status": "X"},
        {"name": "mystery-model", "status": "X"},
    ]

    grouped = _group_models(models)

    assert grouped["Visual Analysis"][0]["name"] == "image-gan"
    assert grouped["Audio Analysis"][0]["name"] == "speech-synth"
    assert grouped["Model Breakdown"][0]["name"] == "mystery-model"
