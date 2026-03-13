from helpers.tool import Tool, Response
from plugins.slack.helpers.slack_client import (
    SlackClient, SlackAPIError, format_messages, get_slack_config,
    get_modes_to_try,
)
from plugins.slack.helpers.sanitize import require_auth, sanitize_channel_name, validate_slack_id
from slack_sdk.errors import SlackApiError


class SlackRead(Tool):
    """Read messages, list channels, or list threads from a Slack workspace."""

    async def execute(self, **kwargs) -> Response:
        channel_id = self.args.get("channel_id", "")
        thread_ts = self.args.get("thread_ts", "")
        limit = int(self.args.get("limit", "50"))
        action = self.args.get("action", "messages")

        # Validate channel_id format when provided
        if channel_id:
            try:
                channel_id = validate_slack_id(channel_id, "channel_id")
            except ValueError as e:
                return Response(message=str(e), break_loop=False)

        config = get_slack_config(self.agent)
        try:
            require_auth(config)
        except ValueError as e:
            return Response(message=f"Auth error: {e}", break_loop=False)

        explicit_mode = self.args.get("mode", "")
        modes = get_modes_to_try(config, explicit_mode or None)

        last_error = None
        for mode in modes:
            try:
                client = SlackClient.from_config(agent=self.agent, mode=mode)

                if action == "channels":
                    types = self.args.get("types", "public_channel,private_channel")
                    channels = await client.get_all_channels(types=types, limit=limit)
                    await client.close()
                    return Response(message=_format_channels(channels), break_loop=False)

                elif action == "threads":
                    if not channel_id:
                        return Response(message="Error: channel_id is required for listing threads.", break_loop=False)
                    if not thread_ts:
                        return Response(message="Error: thread_ts is required for reading thread replies.", break_loop=False)
                    messages = await client.get_thread_replies(channel_id, thread_ts, limit=limit)
                    await client.close()
                    if not messages:
                        return Response(message="No replies found in this thread.", break_loop=False)
                    result = format_messages(messages, include_ids=True)
                    return Response(
                        message=f"Retrieved {len(messages)} messages from thread:\n\n{result}",
                        break_loop=False,
                    )

                elif action == "messages":
                    if not channel_id:
                        return Response(message="Error: channel_id is required.", break_loop=False)

                    oldest = self.args.get("oldest", "")
                    messages = await client.get_all_channel_messages(
                        channel_id=channel_id, limit=limit, oldest=oldest,
                    )
                    await client.close()

                    if not messages:
                        return Response(message="No messages found in the specified channel.", break_loop=False)

                    result = format_messages(messages, include_ids=True)
                    return Response(
                        message=f"Retrieved {len(messages)} messages from channel {channel_id}:\n\n{result}",
                        break_loop=False,
                    )
                else:
                    return Response(
                        message=f"Unknown action '{action}'. Use 'messages', 'channels', or 'threads'.",
                        break_loop=False,
                    )

            except SlackApiError as e:
                try:
                    await client.close()
                except Exception:
                    pass
                last_error = e
                if e.response.status_code == 403 and mode != modes[-1]:
                    continue
                return Response(message=f"Slack API error: {e.response['error']}", break_loop=False)
            except Exception as e:
                return Response(message=f"Error reading Slack: {e}", break_loop=False)

        return Response(message=f"Slack API error: {last_error}", break_loop=False)


def _format_channels(channels: list) -> str:
    if not channels:
        return "No channels found."

    lines = [f"Channels ({len(channels)}):"]
    for ch in channels:
        safe_name = sanitize_channel_name(ch.get("name", "unknown"))
        ch_type = "private" if ch.get("is_private") else "public"
        member_count = ch.get("num_members", "?")
        purpose = ch.get("purpose", {}).get("value", "")[:80]
        suffix = f" — {purpose}" if purpose else ""
        lines.append(
            f"  - [{ch_type}] #{safe_name} (ID: {ch['id']}) "
            f"- {member_count} members{suffix}"
        )
    return "\n".join(lines)
