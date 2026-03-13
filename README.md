# Slack Integration Plugin for Agent Zero

Read, send, and manage messages in Slack workspaces with real-time chat bridge support via Socket Mode.

## Features

- **Read messages** from channels and threads
- **Send messages**, reactions, and file uploads
- **List channels** and workspace members
- **Summarize conversations** using LLM with auto-save to memory
- **Search messages and files** across the workspace
- **Manage channels** — pin/unpin, set topic, archive
- **Chat bridge** — real-time Slack-to-Agent Zero chat via Socket Mode (no public URL needed)
- **Prompt injection defense** — NFKC normalization, zero-width stripping, 40+ injection pattern detection

## Quick Start

1. **Create a Slack App** at [api.slack.com/apps](https://api.slack.com/apps):
   - Enable **Socket Mode** (Settings > Socket Mode)
   - Create an **App-Level Token** (xapp-) with `connections:write` scope
   - Under **OAuth & Permissions**, add bot scopes: `channels:read`, `channels:history`, `channels:manage`, `chat:write`, `reactions:write`, `users:read`, `files:write`, `pins:read`, `pins:write`, `groups:read`, `groups:history`, `im:history`
   - Under **Event Subscriptions > Subscribe to bot events**, add: `message.channels`, `message.groups`, `message.im`
   - Install the app to your workspace to get the **Bot Token** (xoxb-)

2. **Install the plugin**:
   ```bash
   ./install.sh
   ```

3. **Configure** in the WebUI (Settings > External Services > Slack Integration):
   - Paste your Bot Token (xoxb-)
   - Paste your App-Level Token (xapp-)
   - Optionally add a User Token (xoxp-) for search functionality

4. **Restart** Agent Zero to load the plugin

5. **Try it**:
   - "List my Slack channels"
   - "Read the last 20 messages in channel C01ABC23DEF"
   - "Summarize the #general channel"
   - "Send 'Hello!' to channel C01ABC23DEF"

## Tools

| Tool | Description |
|------|-------------|
| `slack_read` | Read messages, list channels, list thread replies |
| `slack_send` | Send messages, reactions, file uploads |
| `slack_members` | List workspace/channel members, get user profiles |
| `slack_summarize` | Summarize channel/thread history using LLM |
| `slack_search` | Search messages/files across workspace (requires user token) |
| `slack_manage` | Pin/unpin, set topic/purpose, archive channels |
| `slack_chat` | Chat bridge control (start/stop, add/remove channels) |

## Chat Bridge

The chat bridge turns Slack into a real-time chat frontend for Agent Zero using **Socket Mode** — no public URL or webhook endpoint required. Works behind firewalls and NATs.

### Setup
1. Ensure both Bot Token and App-Level Token are configured
2. Tell the agent: "Add Slack channel C01ABC23DEF to the chat bridge"
3. Tell the agent: "Start the Slack chat bridge"
4. Users can now chat with Agent Zero in the designated Slack channel

### Security Model

The chat bridge has two modes:

**Restricted mode** (default):
- Direct LLM call via `call_utility_model()`
- NO tool access, NO code execution, NO file access
- The LLM literally cannot perform system operations
- Safe for any user to interact with

**Elevated mode** (opt-in):
- Must be explicitly enabled in plugin settings
- Users authenticate by sending `!auth <key>` as a **direct message** to the bot (key never appears in shared channels)
- If `!auth` is sent in a channel, the message is deleted and the user is redirected to DM
- Grants full Agent Zero access (tools, code, files) across all bridge channels
- Sessions auto-expire (default: 5 minutes)
- Only enable for trusted users in private workspaces

**Additional protections:**
- **User Allowlist**: Restrict bot interaction to specific Slack user IDs
- **Rate limiting**: 10 messages per 60 seconds per user
- **Auth failure lockout**: 5 failures in 5 minutes triggers lockout
- **HMAC comparison**: Constant-time auth key verification prevents timing attacks
- **Auth key protection**: `!auth` messages are auto-deleted and responses are ephemeral (only visible to the requesting user)
- **Content sanitization**: All external content is sanitized before reaching the LLM

## Configuration

Tokens can be set via environment variables:
```bash
export SLACK_BOT_TOKEN="xoxb-..."
export SLACK_APP_TOKEN="xapp-..."
export SLACK_USER_TOKEN="xoxp-..."  # optional, for search
```

Or configure in the WebUI settings panel.

## Requirements

- Agent Zero (any recent version)
- Python packages: `slack-sdk>=3.27`, `aiohttp>=3.9`, `pyyaml>=6.0`
- A Slack workspace with a configured Slack App

## Architecture

```
a0-slack/
├── plugin.yaml              # Plugin manifest
├── default_config.yaml      # Default configuration
├── initialize.py            # Dependency installer
├── install.sh               # Installation script
├── helpers/
│   ├── __init__.py
│   ├── slack_client.py      # Slack Web API wrapper (slack-sdk)
│   ├── slack_bot.py         # Chat bridge bot (Socket Mode)
│   └── sanitize.py          # Prompt injection defense
├── tools/                   # 7 tool implementations
├── prompts/                 # Tool descriptions for LLM
├── api/                     # WebUI API endpoints (CSRF-protected)
├── webui/                   # Dashboard + config pages
├── extensions/              # Auto-start hook
├── skills/                  # 5 user-facing workflows
├── tests/                   # Regression test suite (58+ tests)
└── docs/                    # QUICKSTART, DEVELOPMENT
```

## License

MIT — see [LICENSE](LICENSE)
