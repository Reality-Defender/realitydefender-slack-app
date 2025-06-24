from typing import Any


async def app_home_default(client: Any, event: Any) -> None:
    await client.views_publish(
        user_id=event["user"],
        view={
            "type": "home",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "🙌 _Reality Defender_ is set up and ready to go! 🙌",
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "You can use this app to analyze certain files for content authenticity. Go ahead and try it by right clicking on some posted media.",
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "👀 You can view all your pending analysis with `/analysis-status`",
                    },
                },
                {"type": "divider"},
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": "❗If the app doesn't seem to work, try running `/setup-rd your-key` again\n❓If problems persist, please contact your administrator.",
                        }
                    ],
                },
            ],
        },
    )


async def app_home_first_boot(client: Any, event: Any) -> None:
    await client.views_publish(
        user_id=event["user"],
        view={
            "type": "home",
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "❗ _Reality Defender_ hasn't been configured for your user yet. ❗",
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Use the `/setup-rd your-key` command to add your Reality Defender API key and start using the app.",
                    },
                },
            ],
        },
    )


async def notify_error_user_unavailable(client: Any, trigger_id: str) -> None:
    await client.views_open(
        trigger_id=trigger_id,
        view={
            "type": "modal",
            "title": {"type": "plain_text", "text": "Reality Defender"},
            "close": {"type": "plain_text", "text": "Close"},
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "You need to add your Reality Defender API key before you can use this app.",
                    },
                },
                {
                    "type": "context",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Use the `/setup-rd your-key` command to add your Reality Defender API key and start using the app.",
                    },
                },
            ],
        },
    )


async def notify_acknowledge_analysis_request(
    client: Any, trigger_id: str, unsupported: bool = False
) -> None:
    if unsupported:
        await client.views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "title": {"type": "plain_text", "text": "Reality Defender"},
                "close": {"type": "plain_text", "text": "Close"},
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "There are no supported file types for analysis attached to this message. "
                            "Please try again with a different file type.",
                        },
                    }
                ],
            },
        )
    else:
        # Provide the user some basic feedback.
        await client.views_open(
            trigger_id=trigger_id,
            view={
                "type": "modal",
                "title": {"type": "plain_text", "text": "Reality Defender"},
                "close": {"type": "plain_text", "text": "Close"},
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "Your content is being analyzed by Reality Defender and the results will be "
                            "sent to you shortly.",
                        },
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": "This runs in the background and you can continue using Slack while it's "
                                "processing.",
                            }
                        ],
                    },
                ],
            },
        )


async def notify_error_analysis_request(client: Any, trigger_id: str) -> None:
    await client.views_open(
        trigger_id=trigger_id,
        # A simple view payload for a modal
        view={
            "type": "modal",
            "title": {"type": "plain_text", "text": "Reality Defender"},
            "close": {"type": "plain_text", "text": "Close"},
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "There has been an error while uploading a file for analysis.",
                    },
                }
            ],
        },
    )
