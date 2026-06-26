from __future__ import annotations

import logging

from fastapi import FastAPI, Request, Response
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_bolt.app.async_app import AsyncApp
from slack_bolt.oauth.async_oauth_settings import AsyncOAuthSettings

from reality_defender_slack_app.config import Settings, get_settings
from reality_defender_slack_app.deps import Deps
from reality_defender_slack_app.handlers import register_handlers
from reality_defender_slack_app.services.reality_defender import RDClient
from reality_defender_slack_app.services.storage import build_storage

logger = logging.getLogger(__name__)

# Bot scopes requested during the OAuth install flow. Keep in sync with
# oauth_config.scopes.bot in manifest.json.
BOT_SCOPES = [
    "commands",
    "chat:write",
    "files:read",
    "channels:join",
    "app_mentions:read",
    "links:read",
    "remote_files:read",
]


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app hosting the async Slack Bolt app with OAuth."""
    settings = settings or get_settings()

    # DynamoDB-backed stores in production; file/in-memory locally (see storage).
    storage = build_storage(settings)

    deps = Deps(
        settings=settings,
        rd_client=RDClient(),
        key_store=storage.key_store,
    )

    oauth_settings = AsyncOAuthSettings(
        client_id=settings.slack_client_id,
        client_secret=settings.slack_client_secret,
        scopes=BOT_SCOPES,
        installation_store=storage.installation_store,
        state_store=storage.state_store,
        # The app requests bot scopes only, so Bolt authorizes via find_bot and
        # never reads per-user installer records.
        installation_store_bot_only=True,
        install_path="/slack/install",
        redirect_uri_path="/slack/oauth_redirect",
    )

    # No bot token here: in OAuth mode the token is resolved per request from
    # the installation store, keyed by team_id.
    bolt_app = AsyncApp(
        signing_secret=settings.slack_signing_secret,
        oauth_settings=oauth_settings,
    )
    register_handlers(bolt_app, deps)

    handler = AsyncSlackRequestHandler(bolt_app)
    api = FastAPI()

    @api.post("/slack/events")
    async def slack_events(req: Request) -> Response:
        return await handler.handle(req)

    @api.get("/slack/install")
    async def slack_install(req: Request) -> Response:
        return await handler.handle(req)

    @api.get("/slack/oauth_redirect")
    async def slack_oauth_redirect(req: Request) -> Response:
        return await handler.handle(req)

    @api.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return api
