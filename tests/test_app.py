from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from reality_defender_slack_app.app import App, RequestData


@pytest.fixture
def mock_async_app() -> Generator[MagicMock, Any, None]:
    """Create a mock AsyncApp for testing."""
    with patch("reality_defender_slack_app.app.AsyncApp") as mock_app_class:
        mock_app = MagicMock()
        mock_app.command = MagicMock()
        mock_app.event = MagicMock()
        mock_app.shortcut = MagicMock()
        mock_app.client = AsyncMock()
        mock_app_class.return_value = mock_app
        yield mock_app


@pytest.fixture
def mock_socket_handler() -> Generator[MagicMock, Any, None]:
    """Create a mock AsyncSocketModeHandler for testing."""
    with patch(
        "reality_defender_slack_app.app.AsyncSocketModeHandler"
    ) as mock_handler_class:
        mock_handler = MagicMock()
        mock_handler.start_async = AsyncMock()
        mock_handler_class.return_value = mock_handler
        yield mock_handler


@pytest.fixture
def app(mock_async_app: MagicMock, mock_socket_handler: MagicMock) -> App:
    """Create App instance for testing."""
    return App(slack_bot_token="xoxb-test-token", slack_app_token="xapp-test-token")


def test_app_initialization(app: App) -> None:
    """Test App initialization."""
    assert app.bot_token == "xoxb-test-token"
    assert app.active_users == {}
    assert app.active_requests == {}
    assert app.app is not None
    assert app.handler is not None


def test_app_initialization_with_different_tokens(
    mock_async_app: MagicMock, mock_socket_handler: MagicMock
) -> None:
    """Test App initialization with different token values."""
    app = App(
        slack_bot_token="different-bot-token", slack_app_token="different-app-token"
    )

    assert app.bot_token == "different-bot-token"
    assert app.active_users == {}
    assert app.active_requests == {}


@patch("reality_defender_slack_app.app.requests.get")
def test_download_media(mock_get: MagicMock, app: App) -> None:
    """Test _download_media method."""
    # Mock response
    mock_response = MagicMock()
    mock_response.iter_content.return_value = [b"test content"]
    mock_get.return_value.__enter__.return_value = mock_response

    with patch("builtins.open", mock_open()) as mock_file:
        with patch("reality_defender_slack_app.app.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "20240101_120000"

            filename = app._download_media("https://example.com/test.jpg")

            assert filename == "./_20240101_120000_test.jpg"
            mock_get.assert_called_once_with(
                "https://example.com/test.jpg",
                headers={"Authorization": "Bearer xoxb-test-token"},
                stream=True,
            )
            mock_file.assert_called_once_with(filename, "wb")


@patch("reality_defender_slack_app.app.requests.get")
def test_download_media_with_different_url(mock_get: MagicMock, app: App) -> None:
    """Test _download_media method with different URL."""
    mock_response = MagicMock()
    mock_response.iter_content.return_value = [b"different content"]
    mock_get.return_value.__enter__.return_value = mock_response

    with patch("builtins.open", mock_open()):
        with patch("reality_defender_slack_app.app.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "20240202_130000"

            filename = app._download_media("https://example.com/different.png")

            assert filename == "./_20240202_130000_different.png"
            assert (
                "Bearer xoxb-test-token"
                in mock_get.call_args[1]["headers"]["Authorization"]
            )


@pytest.mark.asyncio
async def test_upload_media(app: App) -> None:
    """Test _upload_media method."""
    mock_rd_client = AsyncMock()
    mock_rd_client.upload.return_value = {
        "request_id": "req123",
        "media_id": "media456",
    }

    with patch("reality_defender_slack_app.app.Path") as mock_path:
        mock_path_instance = MagicMock()
        mock_path.return_value = mock_path_instance

        await app._upload_media(
            mock_rd_client, "user123", "channel456", "message789", "test.jpg"
        )

        # Check that the request was stored
        assert "req123" in app.active_requests
        request_data = app.active_requests["req123"]
        assert request_data["user_id"] == "user123"
        assert request_data["media_id"] == "media456"
        assert request_data["channel_id"] == "channel456"
        assert request_data["message_ts"] == "message789"
        assert request_data["status"] == "pending"

        # Check that file was deleted
        mock_path_instance.unlink.assert_called_once()


@pytest.mark.asyncio
async def test_upload_media_with_different_data(app: App) -> None:
    """Test _upload_media method with different data."""
    mock_rd_client = AsyncMock()
    mock_rd_client.upload.return_value = {
        "request_id": "req456",
        "media_id": "media789",
    }

    with patch("reality_defender_slack_app.app.Path") as mock_path:
        mock_path_instance = MagicMock()
        mock_path.return_value = mock_path_instance

        await app._upload_media(
            mock_rd_client, "user456", "channel789", "message012", "test2.png"
        )

        request_data = app.active_requests["req456"]
        assert request_data["user_id"] == "user456"
        assert request_data["media_id"] == "media789"


@pytest.mark.asyncio
async def test_notify_analysis_complete_artificial(app: App) -> None:
    """Test _notify_analysis_complete with artificial content."""
    app.active_requests["req123"] = {
        "user_id": "user123",
        "channel_id": "channel456",
        "message_ts": "message789",
        "status": "processing",
        "media_id": "media456",
    }

    result = {"score": 0.85, "status": "MANIPULATED"}

    await app._notify_analysis_complete(result, "req123")

    # Check that request was removed
    assert "req123" not in app.active_requests

    # Check that message was sent
    app.app.client.chat_postMessage.assert_called_once()  # type: ignore
    call_args = app.app.client.chat_postMessage.call_args  # type: ignore
    assert call_args[1]["channel"] == "channel456"
    assert call_args[1]["thread_ts"] == "message789"
    assert "MANIPULATED CONTENT DETECTED" in call_args[1]["text"]
    assert "85.00%" in call_args[1]["text"]


@pytest.mark.asyncio
async def test_notify_analysis_complete_authentic(app: App) -> None:
    """Test _notify_analysis_complete with authentic content."""
    app.active_requests["req123"] = {
        "user_id": "user123",
        "channel_id": "channel456",
        "message_ts": "message789",
        "status": "processing",
        "media_id": "media456",
    }

    result = {"score": 0.15, "status": "AUTHENTIC"}

    await app._notify_analysis_complete(result, "req123")

    # Check that message was sent
    app.app.client.chat_postMessage.assert_called_once()  # type: ignore
    call_args = app.app.client.chat_postMessage.call_args  # type: ignore
    assert "appears authentic" in call_args[1]["text"]
    assert "15.00%" in call_args[1]["text"]


@pytest.mark.asyncio
async def test_notify_analysis_complete_unknown(app: App) -> None:
    """Test _notify_analysis_complete with unknown status."""
    app.active_requests["req123"] = {
        "user_id": "user123",
        "channel_id": "channel456",
        "message_ts": "message789",
        "status": "processing",
        "media_id": "media456",
    }

    result = {"score": 0.50, "status": "UNKNOWN"}

    await app._notify_analysis_complete(result, "req123")

    # Check that message was sent
    app.app.client.chat_postMessage.assert_called_once()  # type: ignore
    call_args = app.app.client.chat_postMessage.call_args  # type: ignore
    assert "Could not determine" in call_args[1]["text"]


@pytest.mark.asyncio
async def test_notify_analysis_complete_missing_request(app: App) -> None:
    """Test _notify_analysis_complete with missing request."""
    result = {"score": 0.50, "status": "AUTHENTIC"}

    await app._notify_analysis_complete(result, "nonexistent")

    # Should not send any message
    app.app.client.chat_postMessage.assert_not_called()  # type: ignore


@pytest.mark.asyncio
async def test_notify_analysis_complete_with_missing_score(app: App) -> None:
    """Test _notify_analysis_complete with missing score."""
    app.active_requests["req123"] = {
        "user_id": "user123",
        "channel_id": "channel456",
        "message_ts": "message789",
        "status": "processing",
        "media_id": "media456",
    }

    result = {"status": "AUTHENTIC"}  # No score

    await app._notify_analysis_complete(result, "req123")

    app.app.client.chat_postMessage.assert_called_once()  # type: ignore
    call_args = app.app.client.chat_postMessage.call_args  # type: ignore
    assert "0.00%" in call_args[1]["text"]  # Default score


@pytest.mark.asyncio
async def test_start(app: App) -> None:
    """Test start method."""
    await app.start()

    app.handler.start_async.assert_called_once()  # type: ignore


def test_request_data_structure() -> None:
    """Test RequestData structure."""
    data: RequestData = {
        "user_id": "user123",
        "media_id": "media456",
        "channel_id": "channel789",
        "message_ts": "message123",
        "status": "pending",
    }

    assert data["user_id"] == "user123"
    assert data["media_id"] == "media456"
    assert data["channel_id"] == "channel789"
    assert data["message_ts"] == "message123"
    assert data["status"] == "pending"


def test_request_data_with_different_values() -> None:
    """Test RequestData with different values."""
    data: RequestData = {
        "user_id": "different_user",
        "media_id": "different_media",
        "channel_id": "different_channel",
        "message_ts": "different_message",
        "status": "processing",
    }

    assert data["user_id"] == "different_user"
    assert data["status"] == "processing"


def test_setup_handlers_called(mock_async_app: MagicMock, mock_socket_handler: MagicMock) -> None:
    """Test that _setup_handlers is called during initialization."""
    App("test-bot-token", "test-app-token")

    # Verify that handlers are registered
    assert mock_async_app.command.call_count >= 3  # At least 3 commands
    assert mock_async_app.event.call_count >= 1  # At least 1 event
    assert mock_async_app.shortcut.call_count >= 1  # At least 1 shortcut


def test_app_stores_tokens_correctly(mock_async_app: MagicMock, mock_socket_handler: MagicMock) -> None:
    """Test that App stores tokens correctly."""
    bot_token = "xoxb-very-specific-token"
    app_token = "xapp-very-specific-token"

    app = App(bot_token, app_token)

    assert app.bot_token == bot_token
    # App token is used internally by the handler


def test_app_initializes_empty_collections(mock_async_app: MagicMock, mock_socket_handler: MagicMock) -> None:
    """Test that App initializes empty collections."""
    app = App("token1", "token2")

    assert isinstance(app.active_users, dict)
    assert isinstance(app.active_requests, dict)
    assert len(app.active_users) == 0
    assert len(app.active_requests) == 0


@patch("reality_defender_slack_app.app.requests.get")
def test_download_media_creates_proper_filename(mock_get: MagicMock, app: App) -> None:
    """Test that _download_media creates proper filename format."""
    mock_response = MagicMock()
    mock_response.iter_content.return_value = [b"content"]
    mock_get.return_value.__enter__.return_value = mock_response

    with patch("builtins.open", mock_open()):
        with patch("reality_defender_slack_app.app.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "20240315_143000"

            filename = app._download_media("https://example.com/path/to/file.png")

            # Check filename format
            assert filename.startswith("./_20240315_143000_")
            assert filename.endswith("file.png")


@patch("reality_defender_slack_app.app.requests.get")
def test_download_media_uses_correct_headers(mock_get: MagicMock, app: App) -> None:
    """Test that _download_media uses correct authorization headers."""
    mock_response = MagicMock()
    mock_response.iter_content.return_value = [b"content"]
    mock_get.return_value.__enter__.return_value = mock_response

    with patch("builtins.open", mock_open()):
        with patch("reality_defender_slack_app.app.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "20240315_143000"

            app._download_media("https://example.com/test.jpg")

            # Check headers
            call_args = mock_get.call_args
            headers = call_args[1]["headers"]
            assert headers["Authorization"] == "Bearer xoxb-test-token"
            assert call_args[1]["stream"] is True


@pytest.mark.asyncio
async def test_notify_analysis_complete_formats_message_correctly(app: App) -> None:
    """Test that _notify_analysis_complete formats messages correctly."""
    app.active_requests["req999"] = {
        "user_id": "user999",
        "channel_id": "channel999",
        "message_ts": "message999",
        "status": "processing",
        "media_id": "media999",
    }

    result = {"score": 0.7234, "status": "MANIPULATED"}

    await app._notify_analysis_complete(result, "req999")

    call_args = app.app.client.chat_postMessage.call_args  # type: ignore
    message_text = call_args[1]["text"]

    # Check message formatting
    assert "req999" in message_text
    assert "<@user999>" in message_text
    assert "72.34%" in message_text
    assert "⚠️" in message_text
    assert "MANIPULATED CONTENT DETECTED" in message_text
