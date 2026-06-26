import pytest
from fastapi.testclient import TestClient

from reality_defender_slack_app.app import create_app
from reality_defender_slack_app.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        slack_client_id="123.456",
        slack_client_secret="client-secret",
        slack_signing_secret="signing-secret",
    )


def test_create_app_returns_fastapi(settings: Settings) -> None:
    app = create_app(settings)
    client = TestClient(app)

    resp = client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_app_registers_oauth_and_event_routes(settings: Settings) -> None:
    app = create_app(settings)
    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]

    assert "/slack/events" in paths
    assert "/slack/install" in paths
    assert "/slack/oauth_redirect" in paths
    assert "/health" in paths


def test_install_route_serves_add_to_slack(settings: Settings) -> None:
    """The OAuth install path should respond (Add-to-Slack page or redirect)."""
    app = create_app(settings)
    client = TestClient(app, follow_redirects=False)

    resp = client.get("/slack/install")

    # Bolt returns 200 with an Add-to-Slack page, or a 302 to Slack's authorize.
    assert resp.status_code in (200, 302)
