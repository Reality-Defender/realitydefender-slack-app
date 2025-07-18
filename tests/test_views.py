import pytest
from unittest.mock import AsyncMock
from reality_defender_slack_app.views import (
    app_home_default,
    app_home_first_boot,
    notify_error_user_unavailable,
    notify_acknowledge_analysis_request,
    notify_error_analysis_request,
)


@pytest.mark.asyncio
async def test_app_home_default() -> None:
    """Test app_home_default view."""
    mock_client = AsyncMock()
    mock_event = {"user": "U123456"}

    await app_home_default(mock_client, mock_event)

    mock_client.views_publish.assert_called_once()
    call_args = mock_client.views_publish.call_args

    assert call_args[1]["user_id"] == "U123456"
    assert call_args[1]["view"]["type"] == "home"
    assert len(call_args[1]["view"]["blocks"]) == 5


@pytest.mark.asyncio
async def test_app_home_default_content() -> None:
    """Test app_home_default view content."""
    mock_client = AsyncMock()
    mock_event = {"user": "U123456"}

    await app_home_default(mock_client, mock_event)

    call_args = mock_client.views_publish.call_args
    blocks = call_args[1]["view"]["blocks"]

    # Check that the blocks contain expected content
    assert "Reality Defender" in blocks[0]["text"]["text"]
    assert "analyze certain files" in blocks[1]["text"]["text"]
    assert "/analysis-status" in blocks[2]["text"]["text"]
    assert blocks[3]["type"] == "divider"


@pytest.mark.asyncio
async def test_app_home_first_boot() -> None:
    """Test app_home_first_boot view."""
    mock_client = AsyncMock()
    mock_event = {"user": "U123456"}

    await app_home_first_boot(mock_client, mock_event)

    mock_client.views_publish.assert_called_once()
    call_args = mock_client.views_publish.call_args

    assert call_args[1]["user_id"] == "U123456"
    assert call_args[1]["view"]["type"] == "home"
    assert len(call_args[1]["view"]["blocks"]) == 2


@pytest.mark.asyncio
async def test_app_home_first_boot_content() -> None:
    """Test app_home_first_boot view content."""
    mock_client = AsyncMock()
    mock_event = {"user": "U123456"}

    await app_home_first_boot(mock_client, mock_event)

    call_args = mock_client.views_publish.call_args
    blocks = call_args[1]["view"]["blocks"]

    assert "hasn't been configured" in blocks[0]["text"]["text"]
    assert "/setup-rd your-key" in blocks[1]["text"]["text"]


@pytest.mark.asyncio
async def test_notify_error_user_unavailable() -> None:
    """Test notify_error_user_unavailable view."""
    mock_client = AsyncMock()
    trigger_id = "trigger123"

    await notify_error_user_unavailable(mock_client, trigger_id)

    mock_client.views_open.assert_called_once()
    call_args = mock_client.views_open.call_args

    assert call_args[1]["trigger_id"] == trigger_id
    assert call_args[1]["view"]["type"] == "modal"
    assert call_args[1]["view"]["title"]["text"] == "Reality Defender"


@pytest.mark.asyncio
async def test_notify_error_user_unavailable_content() -> None:
    """Test notify_error_user_unavailable view content."""
    mock_client = AsyncMock()
    trigger_id = "trigger123"

    await notify_error_user_unavailable(mock_client, trigger_id)

    call_args = mock_client.views_open.call_args
    blocks = call_args[1]["view"]["blocks"]

    assert "add your Reality Defender API key" in blocks[0]["text"]["text"]
    assert "/setup-rd your-key" in blocks[1]["text"]["text"]


@pytest.mark.asyncio
async def test_notify_acknowledge_analysis_request_supported() -> None:
    """Test notify_acknowledge_analysis_request with supported files."""
    mock_client = AsyncMock()
    trigger_id = "trigger123"

    await notify_acknowledge_analysis_request(mock_client, trigger_id, unsupported=False)

    mock_client.views_open.assert_called_once()
    call_args = mock_client.views_open.call_args

    assert call_args[1]["trigger_id"] == trigger_id
    assert call_args[1]["view"]["type"] == "modal"
    assert "being analyzed" in call_args[1]["view"]["blocks"][0]["text"]["text"]


@pytest.mark.asyncio
async def test_notify_acknowledge_analysis_request_unsupported() -> None:
    """Test notify_acknowledge_analysis_request with unsupported files."""
    mock_client = AsyncMock()
    trigger_id = "trigger123"

    await notify_acknowledge_analysis_request(mock_client, trigger_id, unsupported=True)

    mock_client.views_open.assert_called_once()
    call_args = mock_client.views_open.call_args

    assert call_args[1]["trigger_id"] == trigger_id
    assert call_args[1]["view"]["type"] == "modal"
    assert "no supported file types" in call_args[1]["view"]["blocks"][0]["text"]["text"]


@pytest.mark.asyncio
async def test_notify_acknowledge_analysis_request_default() -> None:
    """Test notify_acknowledge_analysis_request with default unsupported=False."""
    mock_client = AsyncMock()
    trigger_id = "trigger123"

    await notify_acknowledge_analysis_request(mock_client, trigger_id)

    mock_client.views_open.assert_called_once()
    call_args = mock_client.views_open.call_args

    assert "being analyzed" in call_args[1]["view"]["blocks"][0]["text"]["text"]


@pytest.mark.asyncio
async def test_notify_error_analysis_request() -> None:
    """Test notify_error_analysis_request view."""
    mock_client = AsyncMock()
    trigger_id = "trigger123"

    await notify_error_analysis_request(mock_client, trigger_id)

    mock_client.views_open.assert_called_once()
    call_args = mock_client.views_open.call_args

    assert call_args[1]["trigger_id"] == trigger_id
    assert call_args[1]["view"]["type"] == "modal"
    assert "error while uploading" in call_args[1]["view"]["blocks"][0]["text"]["text"]


@pytest.mark.asyncio
async def test_all_views_have_proper_structure() -> None:
    """Test that all modal views have proper structure."""
    mock_client = AsyncMock()
    trigger_id = "trigger123"

    # Test all modal views
    modal_functions = [
        notify_error_user_unavailable,
        notify_error_analysis_request,
        lambda c, t: notify_acknowledge_analysis_request(c, t, unsupported=True),
        lambda c, t: notify_acknowledge_analysis_request(c, t, unsupported=False),
    ]

    for func in modal_functions:
        mock_client.reset_mock()
        await func(mock_client, trigger_id)

        call_args = mock_client.views_open.call_args
        view = call_args[1]["view"]

        assert view["type"] == "modal"
        assert view["title"]["type"] == "plain_text"
        assert view["title"]["text"] == "Reality Defender"
        assert view["close"]["type"] == "plain_text"
        assert view["close"]["text"] == "Close"
        assert len(view["blocks"]) > 0
