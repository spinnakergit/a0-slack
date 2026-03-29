"""Persistent Slack Socket Mode bot for the chat bridge.
Listens for messages in designated channels and routes them through Agent Zero's LLM.

SECURITY MODEL:
  - Restricted mode (default): Uses call_utility_model() — NO tools, NO code execution,
    NO file access. The LLM literally cannot perform system operations.
  - Elevated mode (opt-in): Authenticated users get full agent loop access via
    context.communicate(). Requires: allow_elevated=true in config + runtime auth
    via !auth <key> in Slack. Sessions expire after a configurable timeout.
"""

import asyncio
import collections
import hmac
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("slack_chat_bridge")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.DEBUG)

# Singleton bot instance and its dedicated event loop thread
_bot_instance: Optional["ChatBridgeBot"] = None
_bot_thread: Optional[threading.Thread] = None
_bot_loop: Optional[asyncio.AbstractEventLoop] = None

CHAT_STATE_FILE = "chat_bridge_state.json"


def _get_state_path() -> Path:
    candidates = [
        Path(__file__).parent.parent / "data" / CHAT_STATE_FILE,
        Path("/a0/usr/plugins/slack/data") / CHAT_STATE_FILE,
        Path("/a0/plugins/slack/data") / CHAT_STATE_FILE,
        Path("/git/agent-zero/usr/plugins/slack/data") / CHAT_STATE_FILE,
    ]
    for p in candidates:
        if p.exists():
            return p
    path = candidates[0]
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_chat_state() -> dict:
    path = _get_state_path()
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return {"channels": {}, "contexts": {}}


def save_chat_state(state: dict):
    from plugins.slack.helpers.sanitize import secure_write_json
    secure_write_json(_get_state_path(), state)


def add_chat_channel(channel_id: str, workspace_id: str = "", label: str = ""):
    state = load_chat_state()
    state.setdefault("channels", {})[channel_id] = {
        "workspace_id": workspace_id,
        "label": label or channel_id,
        "added_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    save_chat_state(state)


def remove_chat_channel(channel_id: str):
    state = load_chat_state()
    state.get("channels", {}).pop(channel_id, None)
    state.get("contexts", {}).pop(channel_id, None)
    save_chat_state(state)


def get_chat_channels() -> dict:
    return load_chat_state().get("channels", {})


def get_context_id(channel_id: str) -> Optional[str]:
    return load_chat_state().get("contexts", {}).get(channel_id)


def set_context_id(channel_id: str, context_id: str):
    state = load_chat_state()
    state.setdefault("contexts", {})[channel_id] = context_id
    save_chat_state(state)


class ChatBridgeBot:
    """Slack bot that bridges messages to Agent Zero's LLM via Socket Mode.

    SECURITY: By default, uses direct LLM calls (call_utility_model) with NO
    tool access. Authenticated users can optionally elevate to full agent loop
    access if allow_elevated is enabled in the plugin config.
    """

    MAX_CHAT_MESSAGE_LENGTH = 4000
    MAX_HISTORY_MESSAGES = 20
    RATE_LIMIT_MAX = 10
    RATE_LIMIT_WINDOW = 60  # seconds
    AUTH_MAX_FAILURES = 5
    AUTH_FAILURE_WINDOW = 300  # 5 minute lockout

    CHAT_SYSTEM_PROMPT = (
        "You are a friendly, helpful AI assistant chatting with users on Slack.\n\n"
        "IMPORTANT CONSTRAINTS:\n"
        "- You are a conversational chat bot ONLY. You have NO access to tools, files, "
        "commands, terminals, or any system resources.\n"
        "- If users ask you to run commands, access files, list directories, execute code, "
        "or perform any system operations, explain that you don't have those capabilities.\n"
        "- NEVER fabricate or make up file listings, directory contents, command outputs, "
        "or system information. You genuinely do not have access to any of these.\n"
        "- Be helpful, friendly, and conversational within these constraints.\n"
        "- You can help with general knowledge, answer questions, have discussions, "
        "write text, brainstorm ideas, and more — just not anything involving system access.\n"
        "- Each message shows the Slack username prefix. Respond naturally to the "
        "conversation.\n"
    )

    def __init__(self, bot_token: str, app_token: str):
        if not bot_token or not bot_token.strip():
            raise ValueError("Bot token must be provided to ChatBridgeBot.")
        if not app_token or not app_token.strip():
            raise ValueError("App token (xapp-) must be provided for Socket Mode.")
        self.bot_token = bot_token
        self.app_token = app_token
        self._handler = None
        self._socket_client = None
        self._web_client = None
        self._running = False
        self._ready = False
        self._bot_info = None
        # Per-user rate limiting
        self._rate_limits: dict[str, collections.deque] = {}
        # Per-channel conversation history
        self._conversations: dict[str, list[dict]] = {}
        # Elevated session tracking
        self._elevated_sessions: dict[str, dict] = {}
        # Auth failure tracking
        self._auth_failures: dict[str, collections.deque] = {}
        # Ready event for startup synchronization
        self._ready_event: Optional[threading.Event] = None

    def _get_config(self) -> dict:
        """Load the Slack plugin configuration."""
        try:
            from plugins.slack.helpers.slack_client import get_slack_config
            return get_slack_config()
        except Exception:
            return {}

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _session_key(self, user_id: str) -> str:
        """Session key is per-user (not per-channel).

        Elevation via DM applies to all bridge channels.
        """
        return user_id

    def _is_elevated(self, user_id: str) -> bool:
        config = self._get_config()
        if not config.get("chat_bridge", {}).get("allow_elevated", False):
            return False
        key = self._session_key(user_id)
        session = self._elevated_sessions.get(key)
        if not session:
            return False
        timeout = config.get("chat_bridge", {}).get("session_timeout", 300)
        if timeout > 0 and time.monotonic() - session["at"] > timeout:
            del self._elevated_sessions[key]
            return False
        return True

    def _get_auth_key(self, config: dict) -> str:
        bridge_config = config.get("chat_bridge", {})
        auth_key = bridge_config.get("auth_key", "")
        if not auth_key and bridge_config.get("allow_elevated", False):
            from plugins.slack.helpers.sanitize import generate_auth_key
            auth_key = generate_auth_key()
            bridge_config["auth_key"] = auth_key
            config["chat_bridge"] = bridge_config
            try:
                from plugins.slack.helpers.sanitize import secure_write_json
                config_candidates = [
                    Path("/a0/usr/plugins/slack/config.json"),
                    Path("/a0/plugins/slack/config.json"),
                    Path(__file__).parent.parent / "config.json",
                ]
                for cp in config_candidates:
                    if cp.exists():
                        existing = json.loads(cp.read_text())
                        existing.setdefault("chat_bridge", {})["auth_key"] = auth_key
                        secure_write_json(cp, existing)
                        logger.info("Auto-generated auth key for elevated mode")
                        break
            except Exception as e:
                logger.warning(f"Could not persist auto-generated auth key: {type(e).__name__}")
        return auth_key

    # ------------------------------------------------------------------
    # Auth command handling
    # ------------------------------------------------------------------

    async def _handle_auth_command(self, text: str, user_id: str, channel_id: str) -> Optional[str]:
        """Handle !auth, !deauth, and !bridge-status commands.
        Returns response text if handled, None if not an auth command.
        """
        text = text.strip()

        if text.lower() in ("!deauth", "!dauth", "!unauth", "!logout", "!logoff"):
            key = self._session_key(user_id)
            if key in self._elevated_sessions:
                del self._elevated_sessions[key]
                logger.info(f"Elevated session ended: user={user_id}")
                return "Session ended. Back to restricted mode in all channels."
            return "No active elevated session."

        if text.lower() in ("!bridge-status", "!status"):
            if self._is_elevated(user_id):
                session = self._elevated_sessions[self._session_key(user_id)]
                elapsed = int(time.monotonic() - session["at"])
                config = self._get_config()
                timeout = config.get("chat_bridge", {}).get("session_timeout", 300)
                if timeout > 0:
                    remaining = max(0, timeout - elapsed)
                    expire_info = f"Session expires in {remaining // 60}m {remaining % 60}s"
                else:
                    expire_info = "Session does not expire"
                return (
                    f"Mode: *Elevated* (full agent access)\n"
                    f"{expire_info}. Use `!deauth` to end."
                )
            else:
                config = self._get_config()
                elevated_available = config.get("chat_bridge", {}).get("allow_elevated", False)
                if elevated_available:
                    return "Mode: *Restricted* (chat only). Send `!auth <key>` as a *direct message* to me to elevate."
                return "Mode: *Restricted* (chat only). Elevated mode is not enabled."

        if text.lower().startswith("!auth"):
            config = self._get_config()
            if not config.get("chat_bridge", {}).get("allow_elevated", False):
                return "Elevated mode is not enabled in the configuration."

            auth_key = self._get_auth_key(config)
            if not auth_key:
                return (
                    "Elevated mode is enabled but no auth key could be generated. "
                    "Check plugin configuration."
                )

            # Rate limit auth failures
            now = time.monotonic()
            if user_id not in self._auth_failures:
                self._auth_failures[user_id] = collections.deque()
            failures = self._auth_failures[user_id]
            while failures and now - failures[0] > self.AUTH_FAILURE_WINDOW:
                failures.popleft()
            if len(failures) >= self.AUTH_MAX_FAILURES:
                return "Too many failed attempts. Please wait before trying again."

            parts = text.split(maxsplit=1)
            provided_key = parts[1].strip() if len(parts) > 1 else ""

            if provided_key and hmac.compare_digest(provided_key, auth_key):
                session_key = self._session_key(user_id)
                self._elevated_sessions[session_key] = {"at": now, "user_id": user_id}
                timeout = config.get("chat_bridge", {}).get("session_timeout", 300)
                if timeout > 0:
                    mins = timeout // 60
                    secs = timeout % 60
                    duration = f"{mins}m" if not secs else f"{mins}m {secs}s"
                    expire_msg = f"Session expires in {duration}."
                else:
                    expire_msg = "Session does not expire."
                logger.info(f"Elevated session granted: user={user_id}")
                return (
                    f"Elevated session active. {expire_msg} "
                    f"You now have full Agent Zero access in all bridge channels. "
                    f"Use `!deauth` to end the session."
                )
            else:
                failures.append(now)
                remaining = self.AUTH_MAX_FAILURES - len(failures)
                logger.warning(f"Failed auth attempt: user={user_id} channel={channel_id}")
                return f"Authentication failed. {remaining} attempt(s) remaining."

        return None

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    async def _safe_handle_message(self, event: dict):
        """Wrapper that ensures exceptions are logged, not silently lost."""
        try:
            await self._handle_message(event)
        except Exception as e:
            logger.error(f"Unhandled error in message handler: {type(e).__name__}: {e}")

    async def _handle_message(self, event: dict):
        """Process an incoming Slack message event."""
        logger.debug(f"Event received: type={event.get('type')} subtype={event.get('subtype')} "
                      f"channel={event.get('channel')} user={event.get('user')} "
                      f"bot_id={event.get('bot_id')}")

        # Ignore bot messages and message edits/deletions
        if event.get("bot_id") or event.get("subtype"):
            logger.debug("Ignoring: bot message or subtype")
            return

        channel_id = event.get("channel", "")
        user_id = event.get("user", "")
        text = event.get("text", "").strip()

        if not text or not channel_id or not user_id:
            logger.debug("Ignoring: missing text/channel/user")
            return

        # Ignore own messages
        if self._bot_info and user_id == self._bot_info.get("user_id"):
            logger.debug("Ignoring: own message")
            return

        # DMs: handle auth commands only (auth key stays private in DM)
        is_dm = channel_id.startswith("D")
        if is_dm:
            logger.debug(f"DM received from user={user_id}: text starts with '!'={text.startswith('!')} len={len(text)}")
            if text.startswith("!"):
                # Apply allowlist to DMs too
                config = self._get_config()
                allowed_users = config.get("chat_bridge", {}).get("allowed_users", [])
                if allowed_users and user_id not in [str(u) for u in allowed_users]:
                    logger.debug(f"DM blocked by allowlist: user={user_id}")
                    return
                logger.info(f"Auth command via DM from user={user_id}: {text.split()[0]}")
                response = await self._handle_auth_command(text, user_id, channel_id)
                if response is not None:
                    # DMs are private — safe to reply normally
                    await self._send_reply(channel_id, response)
                else:
                    logger.debug(f"DM command not recognized: {text[:20]}")
            else:
                logger.debug(f"DM ignored (not a command): {text[:30]}")
            return  # Don't process non-command DMs

        chat_channels = get_chat_channels()
        if channel_id not in chat_channels:
            logger.debug(f"Ignoring: channel {channel_id} not in bridge channels {list(chat_channels.keys())}")
            return

        logger.info(f"Processing message from user={user_id} in channel={channel_id}: {text[:50]}...")

        # User allowlist
        config = self._get_config()
        allowed_users = config.get("chat_bridge", {}).get("allowed_users", [])
        if allowed_users and user_id not in [str(u) for u in allowed_users]:
            return

        # Handle auth commands in channels
        if text.startswith("!"):
            if text.lower().startswith("!auth "):
                # !auth in a channel — redirect to DM for security
                await self._delete_auth_message(channel_id, event.get("ts", ""), user_id)
                await self._send_ephemeral(
                    channel_id, user_id,
                    ":lock: For security, please send `!auth <key>` as a *direct message* to me instead.\n"
                    "Your elevation will apply to all bridge channels."
                )
                return
            # Other commands (!deauth, !status) — OK in channel, respond ephemerally
            response = await self._handle_auth_command(text, user_id, channel_id)
            if response is not None:
                await self._send_ephemeral(channel_id, user_id, response)
                return

        # Content length check
        if len(text) > self.MAX_CHAT_MESSAGE_LENGTH:
            await self._send_reply(
                channel_id,
                f"Message too long ({len(text)} chars). Max: {self.MAX_CHAT_MESSAGE_LENGTH}.",
                thread_ts=event.get("ts"),
            )
            return

        # Rate limiting
        now = time.monotonic()
        if user_id not in self._rate_limits:
            self._rate_limits[user_id] = collections.deque()
        timestamps = self._rate_limits[user_id]
        while timestamps and now - timestamps[0] > self.RATE_LIMIT_WINDOW:
            timestamps.popleft()
        if len(timestamps) >= self.RATE_LIMIT_MAX:
            await self._send_reply(
                channel_id,
                f"Rate limit: max {self.RATE_LIMIT_MAX} messages per {self.RATE_LIMIT_WINDOW}s.",
                thread_ts=event.get("ts"),
            )
            return
        timestamps.append(now)

        # Route based on elevation
        is_elevated = self._is_elevated(user_id)

        try:
            if is_elevated:
                response_text = await self._get_elevated_response(channel_id, text, user_id)
            else:
                response_text = await self._get_agent_response(channel_id, text, user_id)
        except Exception as e:
            logger.error(f"Agent error: {type(e).__name__}")
            response_text = "An error occurred while processing your message."

        await self._send_reply(channel_id, response_text, thread_ts=event.get("ts"))

    # ------------------------------------------------------------------
    # Restricted mode
    # ------------------------------------------------------------------

    async def _get_agent_response(self, channel_id: str, text: str, user_id: str) -> str:
        """Get LLM response via direct model call (no agent loop, no tools)."""
        logger.debug(f"Getting agent response for channel={channel_id} user={user_id}")
        try:
            from agent import AgentContext, AgentContextType
            from initialize import initialize_agent

            context_id = get_context_id(channel_id)
            context = None
            if context_id:
                context = AgentContext.get(context_id)
            if context is None:
                config = initialize_agent()
                context = AgentContext(config=config, type=AgentContextType.USER)
                set_context_id(channel_id, context.id)
                logger.info(f"Created new context {context.id} for channel {channel_id}")

            agent = context.agent0

            from plugins.slack.helpers.sanitize import sanitize_content, sanitize_username
            safe_text = sanitize_content(text)

            # Get username
            author_name = user_id
            try:
                user_info = await self._web_client.users_info(user=user_id)
                profile = user_info.data.get("user", {}).get("profile", {})
                author_name = sanitize_username(
                    profile.get("display_name") or profile.get("real_name") or user_id
                )
            except Exception:
                pass

            if channel_id not in self._conversations:
                self._conversations[channel_id] = []
            history = self._conversations[channel_id]
            history.append({"role": "user", "name": author_name, "content": safe_text})

            if len(history) > self.MAX_HISTORY_MESSAGES:
                self._conversations[channel_id] = history[-self.MAX_HISTORY_MESSAGES:]
                history = self._conversations[channel_id]

            formatted = []
            for msg in history:
                if msg["role"] == "user":
                    formatted.append(f"{msg['name']}: {msg['content']}")
                else:
                    formatted.append(f"Assistant: {msg['content']}")
            conversation_text = "\n".join(formatted)

            logger.debug(f"Calling utility model with {len(history)} messages")
            response = await agent.call_utility_model(
                system=self.CHAT_SYSTEM_PROMPT,
                message=conversation_text,
            )
            logger.debug(f"LLM response received: {len(str(response))} chars")

            history.append({"role": "assistant", "content": response})
            return response if isinstance(response, str) else str(response)

        except ImportError as e:
            logger.error(f"Import error in agent response: {e}")
            return "Agent Zero imports not available. Chat bridge requires running inside A0."

    # ------------------------------------------------------------------
    # Elevated mode
    # ------------------------------------------------------------------

    async def _get_elevated_response(self, channel_id: str, text: str, user_id: str) -> str:
        """Route through the full Agent Zero agent loop."""
        try:
            from agent import AgentContext, AgentContextType, UserMessage
            from initialize import initialize_agent

            context_id = get_context_id(channel_id)
            context = None
            if context_id:
                context = AgentContext.get(context_id)
            if context is None:
                config = initialize_agent()
                context = AgentContext(config=config, type=AgentContextType.USER)
                set_context_id(channel_id, context.id)
                logger.info(f"Created new elevated context {context.id} for channel {channel_id}")

            from plugins.slack.helpers.sanitize import sanitize_content, sanitize_username
            safe_text = sanitize_content(text)

            author_name = user_id
            try:
                user_info = await self._web_client.users_info(user=user_id)
                profile = user_info.data.get("user", {}).get("profile", {})
                author_name = sanitize_username(
                    profile.get("display_name") or profile.get("real_name") or user_id
                )
            except Exception:
                pass

            prefixed_text = (
                f"[Slack Chat Bridge - authenticated message from {author_name}]\n"
                f"{safe_text}"
            )

            user_msg = UserMessage(message=prefixed_text, attachments=[])
            task = context.communicate(user_msg)
            result = await task.result()
            return result if isinstance(result, str) else str(result)

        except ImportError:
            return "Agent Zero imports not available. Elevated mode requires running inside A0."

    # ------------------------------------------------------------------
    # Auth message protection
    # ------------------------------------------------------------------

    async def _delete_auth_message(self, channel_id: str, ts: str, user_id: str):
        """Try to delete the user's !auth message to protect the key.

        Slack bots can only delete their own messages by default. To delete
        others' messages, the bot needs admin-level scope (chat:write with
        admin consent) or the workspace must allow it. If deletion fails,
        we warn the user via ephemeral message.
        """
        if not ts:
            return
        try:
            await self._web_client.chat_delete(channel=channel_id, ts=ts)
            logger.info(f"Deleted !auth message from user={user_id} in channel={channel_id}")
        except Exception as e:
            logger.warning(f"Could not delete !auth message: {type(e).__name__}")
            # Warn the user to delete it themselves
            try:
                await self._web_client.chat_postEphemeral(
                    channel=channel_id,
                    user=user_id,
                    text=(
                        ":warning: *Security notice:* I couldn't delete your `!auth` message. "
                        "Please delete it manually to protect your auth key."
                    ),
                )
            except Exception:
                pass

    async def _send_ephemeral(self, channel_id: str, user_id: str, text: str):
        """Send an ephemeral message (only visible to the specified user)."""
        if not text:
            return
        try:
            await self._web_client.chat_postEphemeral(
                channel=channel_id,
                user=user_id,
                text=text,
            )
        except Exception as e:
            logger.warning(f"Ephemeral send failed, falling back to regular message: {type(e).__name__}")
            # Fallback to regular message if ephemeral fails
            await self._send_reply(channel_id, text)

    # ------------------------------------------------------------------
    # Response sending
    # ------------------------------------------------------------------

    async def _send_reply(self, channel_id: str, text: str, thread_ts: str = ""):
        """Send a response to Slack, splitting long messages."""
        if not text:
            text = "(No response)"
        chunks = _split_message(text)
        for chunk in chunks:
            kwargs = {"channel": channel_id, "text": chunk}
            if thread_ts:
                kwargs["thread_ts"] = thread_ts
            try:
                await self._web_client.chat_postMessage(**kwargs)
            except Exception as e:
                logger.error(f"Failed to send message: {type(e).__name__}")

    # ------------------------------------------------------------------
    # Bot lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        """Start the Socket Mode connection."""
        try:
            from slack_sdk.web.async_client import AsyncWebClient
            from slack_sdk.socket_mode.aiohttp import SocketModeClient
            from slack_sdk.socket_mode.request import SocketModeRequest
            from slack_sdk.socket_mode.response import SocketModeResponse
        except ModuleNotFoundError:
            logger.warning("slack-sdk not found, installing...")
            import subprocess, sys
            python = "/opt/venv-a0/bin/python3" if os.path.isfile("/opt/venv-a0/bin/python3") else sys.executable
            subprocess.check_call([python, "-m", "pip", "install", "slack-sdk>=3.0,<4"], capture_output=True)
            from slack_sdk.web.async_client import AsyncWebClient
            from slack_sdk.socket_mode.aiohttp import SocketModeClient
            from slack_sdk.socket_mode.request import SocketModeRequest
            from slack_sdk.socket_mode.response import SocketModeResponse

        self._web_client = AsyncWebClient(token=self.bot_token)

        # Get bot info
        auth = await self._web_client.auth_test()
        self._bot_info = auth.data
        logger.info(f"Chat bridge authenticated as {self._bot_info.get('user', 'unknown')}")

        self._socket_client = SocketModeClient(
            app_token=self.app_token,
            web_client=self._web_client,
        )

        bot = self

        async def handle_events(client: SocketModeClient, req: SocketModeRequest):
            # Acknowledge immediately
            response = SocketModeResponse(envelope_id=req.envelope_id)
            await client.send_socket_mode_response(response)

            if req.type == "events_api":
                event = req.payload.get("event", {})
                if event.get("type") == "message":
                    # Process in a background task so one slow LLM call
                    # doesn't block subsequent Slack events
                    asyncio.create_task(bot._safe_handle_message(event))

        self._socket_client.socket_mode_request_listeners.append(handle_events)

        self._running = True
        self._ready = True
        if self._ready_event:
            self._ready_event.set()

        await self._socket_client.connect()
        logger.info("Socket Mode connected")

        # Keep the connection alive
        while self._running:
            await asyncio.sleep(1)

    async def stop(self):
        """Stop the Socket Mode connection."""
        self._running = False
        self._ready = False
        if self._socket_client:
            try:
                await self._socket_client.close()
            except Exception:
                pass
        if self._web_client:
            try:
                session = self._web_client.session
                if session and not session.closed:
                    await session.close()
            except Exception:
                pass

    def is_ready(self) -> bool:
        return self._ready

    def is_closed(self) -> bool:
        return not self._running


def _split_message(content: str, max_length: int = 4000) -> list[str]:
    """Split long messages for Slack (4000 char limit)."""
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


def _is_bot_alive() -> bool:
    if _bot_instance is None:
        return False
    if _bot_instance.is_closed():
        return False
    if _bot_thread is None or not _bot_thread.is_alive():
        return False
    return True


def _cleanup_dead_bot():
    global _bot_instance, _bot_thread, _bot_loop
    if not _is_bot_alive():
        _bot_instance = None
        _bot_thread = None
        _bot_loop = None


def _run_bot_in_thread(bot: ChatBridgeBot, ready_event: threading.Event):
    """Run the bot in a dedicated thread with its own event loop."""
    global _bot_instance, _bot_thread, _bot_loop

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _bot_loop = loop

    bot._ready_event = ready_event

    try:
        loop.run_until_complete(bot.start())
    except Exception as e:
        logger.error(f"Chat bridge bot exited with error: {type(e).__name__}: {e}")
    finally:
        logger.info("Chat bridge bot thread ending, cleaning up singleton")
        ready_event.set()
        _bot_instance = None
        _bot_thread = None
        _bot_loop = None
        try:
            loop.close()
        except Exception:
            pass


async def start_chat_bridge(bot_token: str, app_token: str) -> ChatBridgeBot:
    """Start the chat bridge bot in a dedicated background thread."""
    global _bot_instance, _bot_thread, _bot_loop

    if not bot_token or not bot_token.strip():
        raise ValueError("Cannot start chat bridge: bot token is empty or not configured.")
    if not app_token or not app_token.strip():
        raise ValueError(
            "Cannot start chat bridge: app token (xapp-) is required for Socket Mode. "
            "Configure it in the Slack plugin settings."
        )

    _cleanup_dead_bot()

    if _bot_instance and _is_bot_alive():
        return _bot_instance

    # Force-close any leftover instance
    if _bot_instance:
        try:
            if not _bot_instance.is_closed():
                if _bot_loop and _bot_loop.is_running():
                    asyncio.run_coroutine_threadsafe(_bot_instance.stop(), _bot_loop).result(timeout=5)
                else:
                    await _bot_instance.stop()
        except Exception:
            pass
        _bot_instance = None
        _bot_thread = None
        _bot_loop = None

    bot = ChatBridgeBot(bot_token, app_token)
    _bot_instance = bot

    ready_event = threading.Event()
    thread = threading.Thread(
        target=_run_bot_in_thread,
        args=(bot, ready_event),
        daemon=True,
        name="slack-chat-bridge",
    )
    _bot_thread = thread
    thread.start()

    # Use asyncio-safe wait to avoid blocking the caller's event loop
    await asyncio.to_thread(ready_event.wait, 35)

    if not bot.is_ready():
        logger.warning("Bot started but may not be fully ready yet")

    return bot


async def stop_chat_bridge():
    """Stop the chat bridge bot."""
    global _bot_instance, _bot_thread, _bot_loop

    if _bot_instance and not _bot_instance.is_closed():
        if _bot_loop and _bot_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_bot_instance.stop(), _bot_loop)
            try:
                future.result(timeout=10)
            except Exception:
                pass
        else:
            try:
                await _bot_instance.stop()
            except Exception:
                pass

    if _bot_thread and _bot_thread.is_alive():
        _bot_thread.join(timeout=5)

    _bot_instance = None
    _bot_thread = None
    _bot_loop = None


def get_bot_status() -> dict:
    """Get current bot status."""
    _cleanup_dead_bot()

    if _bot_instance is None:
        return {"running": False, "status": "stopped"}
    if _bot_instance.is_closed():
        return {"running": False, "status": "closed"}
    if _bot_thread and not _bot_thread.is_alive():
        return {"running": False, "status": "crashed"}
    if _bot_instance.is_ready():
        info = _bot_instance._bot_info or {}
        return {
            "running": True,
            "status": "connected",
            "user": info.get("user", "unknown"),
            "user_id": info.get("user_id"),
            "team": info.get("team", "unknown"),
            "team_id": info.get("team_id"),
        }
    return {"running": True, "status": "connecting"}
