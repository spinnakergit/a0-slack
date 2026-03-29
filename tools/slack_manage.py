from helpers.tool import Tool, Response
from usr.plugins.slack.helpers.slack_client import (
    SlackClient, get_slack_config,
)
from usr.plugins.slack.helpers.sanitize import require_auth, sanitize_channel_name, validate_slack_id
from slack_sdk.errors import SlackApiError


class SlackManage(Tool):
    """Manage Slack channels: pin/unpin messages, set topic, archive."""

    async def execute(self, **kwargs) -> Response:
        action = self.args.get("action", "")
        channel_id = self.args.get("channel_id", "")

        if not action:
            return Response(
                message="Error: action is required. Use: pin, unpin, list_pins, set_topic, set_purpose, archive.",
                break_loop=False,
            )
        if not channel_id:
            return Response(message="Error: channel_id is required.", break_loop=False)
        try:
            channel_id = validate_slack_id(channel_id, "channel_id")
        except ValueError as e:
            return Response(message=str(e), break_loop=False)

        config = get_slack_config(self.agent)
        try:
            require_auth(config)
        except ValueError as e:
            return Response(message=f"Auth error: {e}", break_loop=False)
        if not (config.get("bot", {}).get("token", "") or "").strip():
            return Response(
                message="Error: Bot token not configured. Management requires a bot account.",
                break_loop=False,
            )

        try:
            client = SlackClient.from_config(agent=self.agent, mode="bot")

            if action == "pin":
                timestamp = self.args.get("timestamp", "")
                if not timestamp:
                    return Response(message="Error: timestamp is required for pinning.", break_loop=False)
                await client.pin_message(channel_id, timestamp)
                await client.close()
                return Response(message=f"Message {timestamp} pinned.", break_loop=True)

            elif action == "unpin":
                timestamp = self.args.get("timestamp", "")
                if not timestamp:
                    return Response(message="Error: timestamp is required for unpinning.", break_loop=False)
                await client.unpin_message(channel_id, timestamp)
                await client.close()
                return Response(message=f"Message {timestamp} unpinned.", break_loop=True)

            elif action == "list_pins":
                items = await client.list_pins(channel_id)
                await client.close()
                if not items:
                    return Response(message="No pinned items in this channel.", break_loop=False)
                lines = [f"Pinned items ({len(items)}):"]
                for item in items:
                    msg = item.get("message", {})
                    text = msg.get("text", "")[:100]
                    user = msg.get("user", "?")
                    ts = msg.get("ts", "?")
                    lines.append(f"  - [{ts}] {user}: {text}")
                return Response(message="\n".join(lines), break_loop=False)

            elif action == "set_topic":
                topic = self.args.get("topic", "")
                if not topic:
                    return Response(message="Error: topic is required.", break_loop=False)
                await client.set_topic(channel_id, topic)
                await client.close()
                return Response(message=f"Channel topic set to: {topic}", break_loop=True)

            elif action == "set_purpose":
                purpose = self.args.get("purpose", "")
                if not purpose:
                    return Response(message="Error: purpose is required.", break_loop=False)
                await client.set_purpose(channel_id, purpose)
                await client.close()
                return Response(message=f"Channel purpose set to: {purpose}", break_loop=True)

            elif action == "archive":
                await client.archive_channel(channel_id)
                await client.close()
                return Response(message=f"Channel {channel_id} archived.", break_loop=True)

            else:
                return Response(
                    message=f"Unknown action '{action}'. Use: pin, unpin, list_pins, set_topic, set_purpose, archive.",
                    break_loop=False,
                )

        except SlackApiError as e:
            return Response(message=f"Slack API error: {e.response['error']}", break_loop=False)
        except Exception as e:
            return Response(message=f"Error: {type(e).__name__}", break_loop=False)
