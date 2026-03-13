from helpers.tool import Tool, Response
from plugins.slack.helpers.slack_client import (
    SlackClient, get_slack_config,
)
from plugins.slack.helpers.sanitize import require_auth, validate_slack_id
from slack_sdk.errors import SlackApiError


class SlackSend(Tool):
    """Send a message, reaction, or file upload to a Slack channel."""

    async def execute(self, **kwargs) -> Response:
        channel_id = self.args.get("channel_id", "")
        content = self.args.get("content", "")
        thread_ts = self.args.get("thread_ts", "")
        action = self.args.get("action", "send")

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
                message="Error: Bot token not configured. Sending requires a bot account.",
                break_loop=False,
            )

        try:
            client = SlackClient.from_config(agent=self.agent, mode="bot")

            if action == "send":
                if not content:
                    return Response(message="Error: content is required for sending.", break_loop=False)

                chunks = _split_message(content)
                sent_ts = []
                for i, chunk in enumerate(chunks):
                    ts = thread_ts if i == 0 and thread_ts else None
                    result = await client.send_message(
                        channel_id=channel_id, text=chunk, thread_ts=ts,
                    )
                    sent_ts.append(result.get("ts", ""))

                await client.close()
                if len(sent_ts) == 1:
                    return Response(message=f"Message sent (ts: {sent_ts[0]}).", break_loop=True)
                return Response(
                    message=f"Message sent in {len(sent_ts)} parts.",
                    break_loop=True,
                )

            elif action == "react":
                emoji = self.args.get("emoji", "")
                timestamp = self.args.get("timestamp", "")
                if not emoji or not timestamp:
                    return Response(
                        message="Error: emoji and timestamp required for reactions.",
                        break_loop=False,
                    )
                # Strip colons if user includes them (e.g., :thumbsup: -> thumbsup)
                emoji = emoji.strip(":")
                await client.add_reaction(channel_id, timestamp, emoji)
                await client.close()
                return Response(
                    message=f"Reaction :{emoji}: added to message {timestamp}.",
                    break_loop=True,
                )

            elif action == "upload":
                filename = self.args.get("filename", "file.txt")
                title = self.args.get("title", "")
                if not content:
                    return Response(message="Error: content is required for upload.", break_loop=False)
                await client.upload_file(
                    channel=channel_id,
                    content=content,
                    filename=filename,
                    title=title,
                    thread_ts=thread_ts,
                )
                await client.close()
                return Response(message=f"File '{filename}' uploaded.", break_loop=True)

            else:
                return Response(
                    message=f"Unknown action '{action}'. Use 'send', 'react', or 'upload'.",
                    break_loop=False,
                )

        except SlackApiError as e:
            return Response(message=f"Slack API error: {e.response['error']}", break_loop=False)
        except Exception as e:
            return Response(message=f"Error sending to Slack: {type(e).__name__}", break_loop=False)


def _split_message(content: str, max_length: int = 4000) -> list[str]:
    if len(content) <= max_length:
        return [content]
    chunks = []
    while content:
        if len(content) <= max_length:
            chunks.append(content)
            break
        split_at = content.rfind("\n", 0, max_length)
        if split_at == -1:
            split_at = content.rfind(" ", 0, max_length)
        if split_at == -1:
            split_at = max_length
        chunks.append(content[:split_at])
        content = content[split_at:].lstrip("\n")
    return chunks
