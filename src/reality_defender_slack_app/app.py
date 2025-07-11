from __future__ import annotations

import array
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, TypedDict

import requests
from realitydefender import RealityDefender
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
from slack_bolt.app.async_app import AsyncApp

from reality_defender_slack_app.views import (
    app_home_default,
    app_home_first_boot,
    notify_acknowledge_analysis_request,
    notify_error_analysis_request,
    notify_error_user_unavailable,
)

logger = logging.getLogger(__name__)


class RequestData(TypedDict):
    user_id: str
    media_id: str
    channel_id: str
    message_ts: str
    status: str


class App:
    """Slack bot that integrates with Reality Defender SDK for content analysis."""

    def __init__(self, slack_bot_token: str, slack_app_token: str):
        """
        Initialize the Slack app.

        Args:
            slack_bot_token: Slack Bot User OAuth Token
            slack_app_token: Slack App-Level Token
        """
        self.bot_token = slack_bot_token
        self.app = AsyncApp(
            name="Reality Defender",
            logger=logger,
            token=self.bot_token,
        )
        self.handler = AsyncSocketModeHandler(self.app, app_token=slack_app_token)

        # Track active user sessions and analysis requests.
        self.active_users: Dict[str, RealityDefender] = {}
        self.active_requests: Dict[str, RequestData] = {}

        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Set up Slack event handlers."""

        @self.app.command("/analyze")
        async def handle_analyze_command(ack: Any, respond: Any, _command: Any) -> None:
            """Handle /analyze slash command."""
            await ack()

            await respond("Command unavailable")
            return

        @self.app.event("app_home_opened")
        async def show_home_tab(client: Any, event: Any) -> None:
            logger.debug(f"Received event: {json.dumps(event, indent=2)}")

            if event.get("user") in self.active_users:
                await app_home_default(client, event)
            else:
                await app_home_first_boot(client, event)

        @self.app.command("/setup-rd")
        async def handle_configure_rd_command(
            ack: Any, respond: Any, command: Any
        ) -> None:
            """Handle /configure-rd slash command."""
            await ack()

            logger.debug(f"Received setup-rd command: {json.dumps(command, indent=2)}")

            self.active_users[command.get("user_id")] = RealityDefender(
                api_key=command.get("text")
            )
            await respond("Your user has been registered.")
            return

        @self.app.command("/analysis-status")
        async def handle_status_command(ack: Any, respond: Any, command: Any) -> None:
            """Handle /analysis-status slash command to check analysis status."""
            await ack()
            logger.debug(
                f"Received analysis-status command: {json.dumps(command, indent=2)}"
            )

            try:
                user_id = command.get("user_id")
                request_id = command.get("text", "").strip()

                if not request_id:
                    # Show all active requests for user
                    user_requests = [
                        req_id
                        for req_id, req_data in self.active_requests.items()
                        if req_data.get("user_id") == user_id
                    ]

                    if user_requests:
                        await respond(
                            f"Your active analyses: {', '.join(user_requests)}"
                        )
                    else:
                        await respond("You have no active analyses.")
                    return

                # Check specific analysis status
                if request_id in self.active_requests:
                    req_data = self.active_requests[request_id]
                    if req_data.get("user_id") == user_id:
                        status = req_data.get("status", "unknown")
                        await respond(f"Analysis `{request_id}` status: {status}")
                    else:
                        await respond(
                            "Analysis not found or you don't have permission to view it."
                        )
                else:
                    await respond(f"Analysis `{request_id}` not found or completed.")

            except Exception as e:
                logger.warning(f"Error handling status command: {e}")
                await respond("❌ An error occurred while checking status.")

        @self.app.shortcut("analyze")
        async def handle_analyze_shortcut(ack: Any, shortcut: Any, client: Any) -> None:
            await ack()

            logger.debug(f"Received analyze shortcut: {json.dumps(shortcut, indent=2)}")
            user_id: str = shortcut.get("user", {}).get("id", "")
            channel_id: str = shortcut.get("channel", {}).get("id", "")
            message_ts: str = shortcut.get("message_ts", "")
            trigger_id: str = shortcut.get("trigger_id", "")

            rd_client: RealityDefender | None = self.active_users.get(user_id)
            if not rd_client:
                await notify_error_user_unavailable(client, trigger_id)
                return

            try:
                blocks: array.array = shortcut.get("message", {}).get("blocks", [])
                files: array.array = shortcut.get("message", {}).get("files", [])

                urls: list = []

                urls.extend(
                    [
                        block.get("image_url") or block.get("slack_file", {}).get("url")
                        for block in blocks
                        if block.get("type") == "image"
                    ]
                )
                urls.extend(
                    [
                        file.get("url_private") or file.get("url_private_download", {})
                        for file in files
                        if file.get("filetype") in ["jpg", "jpeg", "png", "mp4"]
                    ]
                )

                if not urls:
                    await notify_acknowledge_analysis_request(
                        client, trigger_id, unsupported=True
                    )
                    return

                for url in urls:
                    filename = self._download_media(url)
                    await self._upload_media(
                        rd_client, user_id, channel_id, message_ts, filename
                    )

                await notify_acknowledge_analysis_request(client, trigger_id)

            except Exception:
                logger.warning("Error handling analyze shortcut", exc_info=True)
                # Surely this should be more informative.
                await notify_error_analysis_request(client, trigger_id)

    async def start(self) -> None:
        await self.handler.start_async()

    def _download_media(self, url: str) -> str:
        # Create a unique filename.
        filename = f"./_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{url.split('/')[-1]}"

        with (
            requests.get(
                url,
                headers={"Authorization": "Bearer " + self.bot_token},
                stream=True,
            ) as r,
            open(filename, "wb") as f,
        ):
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        return filename

    async def _upload_media(
        self,
        rd_client: RealityDefender,
        user_id: str,
        channel_id: str,
        message_ts: str,
        filename: str,
    ) -> None:
        """Upload media to Reality Defender."""
        upload_result = await rd_client.upload(file_path=filename)
        self.active_requests[upload_result["request_id"]] = {
            "user_id": user_id,
            "media_id": upload_result["media_id"],
            "channel_id": channel_id,
            "message_ts": message_ts,
            "status": "pending",
        }
        Path(filename).unlink()

    async def poll_results(self) -> None:
        """
        Poll for analysis results and notify when complete.
        """
        while True:
            for request_id in self.active_requests.keys():
                request: RequestData | None = self.active_requests.get(request_id)
                if request and request.get("status") == "pending":
                    rd_client: RealityDefender | None = self.active_users.get(
                        request["user_id"]
                    )
                    if rd_client:
                        request["status"] = "processing"

                        async def analysis() -> None:
                            """
                            Run analysis and wait for completion.
                            """
                            result = await rd_client.get_result(
                                request_id, max_attempts=60
                            )

                            await self._notify_analysis_complete(result, request_id)

                        asyncio.create_task(analysis())

            await asyncio.sleep(5)

    async def _notify_analysis_complete(self, result: Any, request_id: str) -> None:
        """
        Notify users that analysis is complete.

        Args:
            result: the result of the analysis
            request_id: Analysis ID
        """
        logger.debug(
            f"Notifying analysis complete for {request_id}: {json.dumps(result, indent=2)}"
        )
        try:
            req_data: RequestData | None = self.active_requests.pop(request_id, None)
            if not req_data:
                return

            channel_id: str = req_data["channel_id"]
            user_id: str = req_data["user_id"]
            message_ts: str = req_data["message_ts"]

            # Format results
            confidence_score: float = result.get("score") or 0.0
            status: str = result.get("status", "UNKNOWN")

            # Create a result message
            if status == "ARTIFICIAL":
                status_emoji = "⚠️"
                status_text = "ARTIFICIAL CONTENT DETECTED"
            elif status == "AUTHENTIC":
                status_emoji = "✅"
                status_text = "Content appears authentic"
            else:
                status_emoji = "❓"
                status_text = (
                    "Could not determine content authenticity. Please try again later."
                )

            message = f"""{status_emoji} **Analysis Complete** - ID: `{request_id}`
<@{user_id}> Your content analysis is ready:
**Result:** {status_text}
**Confidence:** {confidence_score:.2%}
            """.strip()

            # Send notification
            await self.app.client.chat_postMessage(
                channel=channel_id, text=message, thread_ts=message_ts
            )

        except Exception as e:
            logger.warning(
                f"Error notifying analysis complete for {request_id}: {e}",
                exc_info=True,
            )
