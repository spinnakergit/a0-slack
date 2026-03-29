"""Slack Web API client wrapper using slack-sdk.

Provides a lightweight async wrapper around the Slack Web API with
rate limiting, bot/user token modes, and message formatting.
"""

import asyncio
import logging
import os
import time
from typing import Optional

logger = logging.getLogger("slack_client")

try:
    from slack_sdk.web.async_client import AsyncWebClient
    from slack_sdk.errors import SlackApiError
except ModuleNotFoundError:
    logger.warning("slack-sdk not found, installing...")
    import subprocess, sys
    python = "/opt/venv-a0/bin/python3" if os.path.isfile("/opt/venv-a0/bin/python3") else sys.executable
    subprocess.check_call([python, "-m", "pip", "install", "slack-sdk>=3.0,<4"], capture_output=True)
    from slack_sdk.web.async_client import AsyncWebClient
    from slack_sdk.errors import SlackApiError


def get_slack_config(agent=None):
    """Load Slack config through the plugin framework with env var overrides."""
    try:
        from helpers import plugins
        config = plugins.get_plugin_config("slack", agent=agent) or {}
    except Exception:
        config = {}

    # Environment variables override file config
    if os.environ.get("SLACK_BOT_TOKEN"):
        config.setdefault("bot", {})["token"] = os.environ["SLACK_BOT_TOKEN"]
    if os.environ.get("SLACK_APP_TOKEN"):
        config.setdefault("bot", {})["app_token"] = os.environ["SLACK_APP_TOKEN"]
    if os.environ.get("SLACK_USER_TOKEN"):
        config.setdefault("user", {})["token"] = os.environ["SLACK_USER_TOKEN"]
    return config


class RateLimiter:
    """Respects Slack's rate limit headers (Retry-After)."""

    def __init__(self):
        self._limits: dict[str, float] = {}

    async def wait(self, bucket: str):
        now = time.monotonic()
        if bucket in self._limits and self._limits[bucket] > now:
            await asyncio.sleep(self._limits[bucket] - now)

    def update(self, bucket: str, retry_after: float):
        if retry_after > 0:
            self._limits[bucket] = time.monotonic() + retry_after


class SlackClient:
    """Lightweight Slack Web API client supporting bot and user token modes."""

    def __init__(self, token: str, is_bot: bool = True):
        self.token = token
        self.is_bot = is_bot
        self._client = AsyncWebClient(token=token)
        self._rate_limiter = RateLimiter()

    @classmethod
    def from_config(cls, agent=None, mode: str = "bot") -> "SlackClient":
        config = get_slack_config(agent)
        if mode == "bot":
            token = config.get("bot", {}).get("token")
            if not token:
                raise ValueError(
                    "Bot token not configured. Set SLACK_BOT_TOKEN env var "
                    "or configure in Slack plugin settings."
                )
            return cls(token=token, is_bot=True)
        elif mode == "user":
            token = config.get("user", {}).get("token")
            if not token:
                raise ValueError(
                    "User token not configured. Set SLACK_USER_TOKEN env var "
                    "or configure in Slack plugin settings."
                )
            return cls(token=token, is_bot=False)
        else:
            raise ValueError(f"Unknown mode: {mode}. Use 'bot' or 'user'.")

    async def close(self):
        """Close the underlying aiohttp session if open."""
        session = self._client.session
        if session and not session.closed:
            await session.close()

    async def _call(self, method: str, **kwargs):
        """Call a Slack Web API method with rate limiting."""
        bucket = method
        await self._rate_limiter.wait(bucket)
        try:
            response = await getattr(self._client, method)(**kwargs)
            return response
        except SlackApiError as e:
            resp = e.response
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", 1.0))
                self._rate_limiter.update(bucket, retry_after)
                await asyncio.sleep(retry_after)
                return await self._call(method, **kwargs)
            raise

    # --- Auth ---

    async def auth_test(self) -> dict:
        """Test authentication and get bot/user info."""
        resp = await self._call("auth_test")
        return resp.data

    # --- Channels / Conversations ---

    async def list_channels(
        self, types: str = "public_channel,private_channel",
        limit: int = 200, cursor: str = "",
    ) -> dict:
        """List conversations the token has access to."""
        kwargs = {"types": types, "limit": min(limit, 1000), "exclude_archived": True}
        if cursor:
            kwargs["cursor"] = cursor
        resp = await self._call("conversations_list", **kwargs)
        return resp.data

    async def get_all_channels(
        self, types: str = "public_channel,private_channel", limit: int = 500,
    ) -> list:
        """Fetch all channels with automatic cursor pagination."""
        all_channels = []
        cursor = ""
        while len(all_channels) < limit:
            batch_size = min(200, limit - len(all_channels))
            data = await self.list_channels(types=types, limit=batch_size, cursor=cursor)
            channels = data.get("channels", [])
            all_channels.extend(channels)
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor or not channels:
                break
        return all_channels[:limit]

    async def get_channel_info(self, channel_id: str) -> dict:
        """Get channel info."""
        resp = await self._call("conversations_info", channel=channel_id)
        return resp.data.get("channel", {})

    async def get_channel_messages(
        self, channel_id: str, limit: int = 50,
        oldest: str = "", latest: str = "", cursor: str = "",
    ) -> dict:
        """Fetch conversation history."""
        kwargs = {"channel": channel_id, "limit": min(limit, 100)}
        if oldest:
            kwargs["oldest"] = oldest
        if latest:
            kwargs["latest"] = latest
        if cursor:
            kwargs["cursor"] = cursor
        resp = await self._call("conversations_history", **kwargs)
        return resp.data

    async def get_all_channel_messages(
        self, channel_id: str, limit: int = 200, oldest: str = "",
    ) -> list:
        """Fetch up to `limit` messages with automatic pagination."""
        all_messages = []
        cursor = ""
        while len(all_messages) < limit:
            batch_size = min(100, limit - len(all_messages))
            data = await self.get_channel_messages(
                channel_id, limit=batch_size, oldest=oldest, cursor=cursor,
            )
            messages = data.get("messages", [])
            all_messages.extend(messages)
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor or not messages:
                break
        return all_messages[:limit]

    # --- Threads ---

    async def get_thread_replies(
        self, channel_id: str, thread_ts: str, limit: int = 100,
    ) -> list:
        """Fetch replies in a thread."""
        kwargs = {"channel": channel_id, "ts": thread_ts, "limit": min(limit, 200)}
        resp = await self._call("conversations_replies", **kwargs)
        return resp.data.get("messages", [])

    # --- Sending ---

    async def send_message(
        self, channel_id: str, text: str, thread_ts: Optional[str] = None,
    ) -> dict:
        """Send a message to a channel."""
        kwargs = {"channel": channel_id, "text": text}
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        resp = await self._call("chat_postMessage", **kwargs)
        return resp.data

    async def add_reaction(self, channel_id: str, timestamp: str, name: str) -> None:
        """Add a reaction to a message."""
        await self._call(
            "reactions_add", channel=channel_id, timestamp=timestamp, name=name,
        )

    async def upload_file(
        self, channel: str, content: str = "", filename: str = "file.txt",
        title: str = "", initial_comment: str = "", thread_ts: str = "",
    ) -> dict:
        """Upload file content to a channel."""
        kwargs = {
            "channel": channel,
            "content": content,
            "filename": filename,
        }
        if title:
            kwargs["title"] = title
        if initial_comment:
            kwargs["initial_comment"] = initial_comment
        if thread_ts:
            kwargs["thread_ts"] = thread_ts
        resp = await self._call("files_upload_v2", **kwargs)
        return resp.data

    # --- Members ---

    async def list_members(self, channel_id: str, limit: int = 200) -> list:
        """List members in a channel."""
        resp = await self._call(
            "conversations_members", channel=channel_id, limit=min(limit, 1000),
        )
        return resp.data.get("members", [])

    async def list_workspace_members(self, limit: int = 200, cursor: str = "") -> dict:
        """List all workspace members."""
        kwargs = {"limit": min(limit, 200)}
        if cursor:
            kwargs["cursor"] = cursor
        resp = await self._call("users_list", **kwargs)
        return resp.data

    async def get_user_info(self, user_id: str) -> dict:
        """Get user profile info."""
        resp = await self._call("users_info", user=user_id)
        return resp.data.get("user", {})

    # --- Search ---

    async def search_messages(
        self, query: str, count: int = 20, sort: str = "timestamp",
    ) -> dict:
        """Search messages across workspace. Requires user token."""
        resp = await self._call(
            "search_messages", query=query, count=min(count, 100), sort=sort,
        )
        return resp.data

    async def search_files(self, query: str, count: int = 20) -> dict:
        """Search files across workspace. Requires user token."""
        resp = await self._call(
            "search_files", query=query, count=min(count, 100),
        )
        return resp.data

    # --- Channel management ---

    async def set_topic(self, channel_id: str, topic: str) -> dict:
        """Set channel topic."""
        resp = await self._call("conversations_setTopic", channel=channel_id, topic=topic)
        return resp.data

    async def set_purpose(self, channel_id: str, purpose: str) -> dict:
        """Set channel purpose."""
        resp = await self._call("conversations_setPurpose", channel=channel_id, purpose=purpose)
        return resp.data

    async def archive_channel(self, channel_id: str) -> dict:
        """Archive a channel."""
        resp = await self._call("conversations_archive", channel=channel_id)
        return resp.data

    async def pin_message(self, channel_id: str, timestamp: str) -> dict:
        """Pin a message in a channel."""
        resp = await self._call("pins_add", channel=channel_id, timestamp=timestamp)
        return resp.data

    async def unpin_message(self, channel_id: str, timestamp: str) -> dict:
        """Unpin a message in a channel."""
        resp = await self._call("pins_remove", channel=channel_id, timestamp=timestamp)
        return resp.data

    async def list_pins(self, channel_id: str) -> list:
        """List pinned items in a channel."""
        resp = await self._call("pins_list", channel=channel_id)
        return resp.data.get("items", [])


def get_modes_to_try(config, explicit_mode=None):
    """Get ordered list of auth modes to try.

    If explicit_mode is set, only that mode is returned.
    Otherwise, bot first, then user if available.
    """
    if explicit_mode and explicit_mode in ("bot", "user"):
        return [explicit_mode]

    has_bot = bool(config.get("bot", {}).get("token"))
    has_user = bool(config.get("user", {}).get("token"))

    if has_bot and has_user:
        return ["bot", "user"]
    elif has_bot:
        return ["bot"]
    elif has_user:
        return ["user"]
    else:
        return ["bot"]  # Will fail with clear "no token" error


class SlackAPIError(Exception):
    def __init__(self, error: str, method: str = ""):
        self.error = error
        self.method = method
        super().__init__(f"Slack API error on {method}: {error}")


def format_messages(messages: list, include_ids: bool = False, user_cache: dict = None) -> str:
    """Format Slack messages into readable text for LLM consumption.

    All external content (usernames, message text) is
    sanitized to neutralise prompt injection attempts.
    """
    from plugins.slack.helpers.sanitize import (
        sanitize_content, sanitize_username,
    )

    cache = user_cache or {}
    lines = []
    for msg in reversed(messages):  # Chronological order
        user_id = msg.get("user", "")
        username = cache.get(user_id, user_id)
        if "username" in msg:
            username = msg["username"]
        username = sanitize_username(username)

        ts = msg.get("ts", "")
        # Convert ts to readable time
        try:
            ts_float = float(ts)
            import datetime
            timestamp = datetime.datetime.fromtimestamp(ts_float).strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError, OSError):
            timestamp = ts[:19] if ts else ""

        content = sanitize_content(msg.get("text", ""))

        # Thread indicator
        thread_text = ""
        if msg.get("thread_ts") and msg.get("thread_ts") != msg.get("ts"):
            thread_text = " (in thread)"
        reply_count = msg.get("reply_count", 0)
        if reply_count:
            thread_text = f" [{reply_count} replies]"

        # File attachments
        files = msg.get("files", [])
        file_text = ""
        if files:
            from plugins.slack.helpers.sanitize import sanitize_filename
            names = [sanitize_filename(f.get("name", "file")) for f in files]
            file_text = f" [Files: {', '.join(names)}]"

        prefix = f"[{ts}] " if include_ids else ""
        lines.append(
            f"{prefix}[{timestamp}] {username}{thread_text}: {content}{file_text}"
        )

    return "\n".join(lines)
