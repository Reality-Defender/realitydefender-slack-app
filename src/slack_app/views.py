from typing import Any


async def app_home_default(client: Any, event: Any) -> None:
    await client.views_open(
        user_id=event["user"],
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
                        "text": "You have configured the Reality Defender app already. You can use this app to analyze "
                        "certain file types for content authenticity. If for any reason the app does not "
                        "work as expected, you can always re-add your API key using the /configure-rd command.",
                    },
                }
            ],
        },
    )


async def app_home_first_boot(client: Any, event: Any) -> None:
    await client.views_open(
        user_id=event["user"],
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
                        "text": "Use the /configure-rd command to add your Reality Defender API key and start using the app.",
                    },
                }
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
                        "text": "You need to add your Reality Defender API key before you can use this bot.",
                    },
                }
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
