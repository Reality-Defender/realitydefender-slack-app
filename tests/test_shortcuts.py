from reality_defender_slack_app.services import media

# Covers collect_media (pure media-extraction logic). The shortcut handler's
# modal/UI behavior is intentionally left untested while that output evolves.


def test_collect_media_includes_supported_file() -> None:
    message = {
        "files": [
            {"mimetype": "image/png", "url_private_download": "u1", "name": "a.png"}
        ]
    }
    assert media.collect_media(message) == [("u1", "a.png")]


def test_collect_media_skips_unsupported_file() -> None:
    message = {"files": [{"mimetype": "application/zip", "url_private": "u", "name": "z"}]}
    assert media.collect_media(message) == []


def test_collect_media_includes_image_block() -> None:
    message = {"blocks": [{"type": "image", "image_url": "img1"}]}
    assert media.collect_media(message) == [("img1", "image")]


def test_collect_media_empty_message() -> None:
    assert media.collect_media({}) == []
