from helpers.tool import Tool, Response
from plugins.slack.helpers.slack_client import (
    SlackClient, get_slack_config, get_modes_to_try,
)
from plugins.slack.helpers.sanitize import (
    require_auth, sanitize_content, sanitize_username, sanitize_channel_name,
)
from slack_sdk.errors import SlackApiError


class SlackSearch(Tool):
    """Search messages or files across a Slack workspace."""

    async def execute(self, **kwargs) -> Response:
        query = self.args.get("query", "")
        action = self.args.get("action", "messages")
        count = int(self.args.get("count", "20"))

        if not query:
            return Response(message="Error: query is required.", break_loop=False)

        config = get_slack_config(self.agent)
        try:
            require_auth(config)
        except ValueError as e:
            return Response(message=f"Auth error: {e}", break_loop=False)

        # Search requires user token
        user_token = (config.get("user", {}).get("token", "") or "").strip()
        if not user_token:
            return Response(
                message="Error: Search requires a user token (xoxp-). "
                        "Configure it in the Slack plugin settings.",
                break_loop=False,
            )

        try:
            client = SlackClient.from_config(agent=self.agent, mode="user")

            if action == "messages":
                self.set_progress("Searching messages...")
                data = await client.search_messages(query=query, count=count)
                await client.close()
                return Response(message=_format_message_results(data, query), break_loop=False)

            elif action == "files":
                self.set_progress("Searching files...")
                data = await client.search_files(query=query, count=count)
                await client.close()
                return Response(message=_format_file_results(data, query), break_loop=False)

            else:
                return Response(
                    message=f"Unknown action '{action}'. Use 'messages' or 'files'.",
                    break_loop=False,
                )

        except SlackApiError as e:
            return Response(message=f"Slack API error: {e.response['error']}", break_loop=False)
        except Exception as e:
            return Response(message=f"Error searching Slack: {e}", break_loop=False)


def _format_message_results(data: dict, query: str) -> str:
    messages_data = data.get("messages", {})
    total = messages_data.get("total", 0)
    matches = messages_data.get("matches", [])

    if not matches:
        return f"No messages found matching '{query}'."

    lines = [f"Found {total} message(s) matching '{query}' (showing {len(matches)}):"]
    for msg in matches:
        username = sanitize_username(msg.get("username", "Unknown"))
        channel_name = sanitize_channel_name(
            msg.get("channel", {}).get("name", "?")
        )
        text = sanitize_content(msg.get("text", ""), max_length=200)
        ts = msg.get("ts", "")
        try:
            ts_float = float(ts)
            import datetime
            timestamp = datetime.datetime.fromtimestamp(ts_float).strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError, OSError):
            timestamp = ""

        lines.append(
            f"\n  [{timestamp}] @{username} in #{channel_name}:\n"
            f"    {text}"
        )
        if msg.get("permalink"):
            lines.append(f"    Link: {msg['permalink']}")

    return "\n".join(lines)


def _format_file_results(data: dict, query: str) -> str:
    files_data = data.get("files", {})
    total = files_data.get("total", 0)
    matches = files_data.get("matches", [])

    if not matches:
        return f"No files found matching '{query}'."

    lines = [f"Found {total} file(s) matching '{query}' (showing {len(matches)}):"]
    for f in matches:
        name = f.get("name", "unknown")
        filetype = f.get("filetype", "?")
        user = sanitize_username(f.get("username", "Unknown"))
        size = f.get("size", 0)
        size_str = f"{size / 1024:.1f}KB" if size < 1024 * 1024 else f"{size / (1024 * 1024):.1f}MB"
        lines.append(
            f"  - {name} ({filetype}, {size_str}) by @{user}"
        )

    return "\n".join(lines)
