from __future__ import annotations

import array
import asyncio
import logging
from asyncio import Task
from functools import partial
from pathlib import Path

import requests
from typing import Dict, Any, TypedDict
from datetime import datetime

from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler

from realitydefender import RealityDefender
from slack_bolt.app.async_app import AsyncApp

from slack_app.views import (
    app_home_default,
    app_home_first_boot,
    notify_error_user_unavailable,
    notify_acknowledge_analysis_request,
    notify_error_analysis_request,
)

logger = logging.getLogger(__name__)


class RequestData(TypedDict):
    user_id: str
    media_id: str
    message_ts: str
    channel_id: str
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
        self.app = AsyncApp(
            name="Reality Defender",
            logger=logger,
            token=slack_bot_token,

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
            ack()

            respond("Command unavailable")
            return

        @self.app.event("app_home_opened")
        async def show_home_tab(client: Any, event: Any, _logger: Any) -> None:
            if event.get("user") in self.active_users:
                app_home_default(client, event)
            else:
                app_home_first_boot(client, event)

        @self.app.command("/configure-rd")
        async def handle_configure_rd_command(
            ack: Any, respond: Any, command: Any
        ) -> None:
            """Handle /configure-rd slash command."""
            ack()
            self.active_users[command.get("user_id")] = RealityDefender(
                {"api_key": command.get("text")}
            )
            respond("Your user has been registered.")
            return

        @self.app.command("/analysis-status")
        async def handle_status_command(ack: Any, respond: Any, command: Any) -> None:
            """Handle /analysis-status slash command to check analysis status."""
            ack()

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
                        respond(f"Your active analyses: {', '.join(user_requests)}")
                    else:
                        respond("You have no active analyses.")
                    return

                # Check specific analysis status
                if request_id in self.active_requests:
                    req_data = self.active_requests[request_id]
                    if req_data.get("user_id") == user_id:
                        status = req_data.get("status", "unknown")
                        respond(f"Analysis `{request_id}` status: {status}")
                    else:
                        respond(
                            "Analysis not found or you don't have permission to view it."
                        )
                else:
                    respond(f"Analysis `{request_id}` not found or completed.")

            except Exception as e:
                logger.error(f"Error handling status command: {e}")
                respond("❌ An error occurred while checking status.")

        @self.app.shortcut("analyze")
        async def handle_analyze_shortcut(ack: Any, shortcut: Any, client: Any) -> None:
            ack()

            try:
                user_id: str = shortcut.get("user", {}).get("id")
                channel_id: str = shortcut.get("channel", {}).get("id")
                blocks: array.array = shortcut.get("message", {}).get("blocks", [])

                for block in blocks:
                    if block.get("type") == "image":
                        filename = self._download_image(block)
                        rd_client: RealityDefender | None = self.active_users.get(
                            user_id
                        )
                        if not rd_client:
                            notify_error_user_unavailable(client, shortcut)
                            return

                        upload_result = await rd_client.upload({"file_path": filename})
                        self.active_requests[upload_result["request_id"]] = {
                            "user_id": user_id,
                            "media_id": upload_result["media_id"],
                            "message_ts": shortcut["message"]["ts"],
                            "channel_id": channel_id,
                            "status": "pending",
                        }
                        Path(filename).unlink()

                        notify_acknowledge_analysis_request(client, shortcut)
                    else:
                        notify_acknowledge_analysis_request(
                            client, shortcut, unsupported=True
                        )

            except Exception:
                # Surely this should be more informative.
                notify_error_analysis_request(client, shortcut)

    async def start(self) -> None:
        await self.handler.start_async()

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
                        complete = partial(
                            self._notify_analysis_complete, request_id=request_id
                        )
                        asyncio.create_task(
                            rd_client.get_result(request_id)
                        ).add_done_callback(complete)

            await asyncio.sleep(5)

    def _download_image(self, block: dict) -> str:
        url = block.get("image_url") or block.get("slack_file", {}).get("url")
        if not url:
            raise Exception("Missing image URL")

        # Create a unique filename.
        filename = f"./_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{url.split('/')[-1]}"

        with (
            requests.get(
                url,
                headers={"Authorization": "Bearer " + self.handler.app_token},
                stream=True,
            ) as r,
            open(filename, "wb") as f,
        ):
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

        return filename

    async def _notify_analysis_complete(self, request_id: str, task: Task) -> None:
        """
        Notify users that analysis is complete.

        Args:
            request_id: Analysis ID
            task: Task object for the analysis
        """
        result = task.result()
        try:
            req_data = self.active_requests.pop(request_id, None)
            if not req_data:
                return

            channel_id = req_data["channel_id"]
            user_id = req_data["user_id"]

            # Format results
            confidence_score = result.get("confidence_score", 0)
            is_synthetic = result.get("is_synthetic", False)
            analysis_type = result.get("analysis_type", "unknown")

            # Create result message
            status_emoji = "⚠️" if is_synthetic else "✅"
            status_text = (
                "SYNTHETIC CONTENT DETECTED"
                if is_synthetic
                else "Content appears authentic"
            )

            message = f"""
{status_emoji} **Analysis Complete** - ID: `{request_id}`

<@{user_id}> Your content analysis is ready:

**Result:** {status_text}
**Confidence:** {confidence_score:.2%}
**Analysis Type:** {analysis_type}

*Analysis completed at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
            """.strip()

            # Send notification
            await self.app.client.chat_postMessage(channel=channel_id, text=message)

        except Exception as e:
            logger.error(f"Error notifying analysis complete for {request_id}: {e}")
