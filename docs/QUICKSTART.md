# Slack Plugin — Quick Start

## Prerequisites

- Agent Zero instance (Docker or local)
- A Slack workspace where you can create apps
- Admin access to install a Slack app

## Step 1: Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App** > **From scratch**
3. Name it (e.g., "Agent Zero") and select your workspace

### Enable Socket Mode
1. Go to **Settings > Socket Mode**
2. Toggle it **ON**
3. Create an App-Level Token with `connections:write` scope
4. Save the token (starts with `xapp-`)

### Add Bot Scopes
1. Go to **OAuth & Permissions > Scopes**
2. Add these **Bot Token Scopes**:
   - `channels:read` — List channels
   - `channels:history` — Read messages
   - `channels:manage` — Set topic/purpose, archive
   - `chat:write` — Send messages, ephemeral messages
   - `reactions:write` — Add reactions
   - `users:read` — List members
   - `files:write` — Upload files
   - `pins:read` — List pinned messages
   - `pins:write` — Pin/unpin messages
   - `groups:read` — Private channels
   - `groups:history` — Private channel messages
   - `im:history` — Receive direct messages (for DM-based auth)

### Add Event Subscriptions
1. Go to **Event Subscriptions**
2. Under **Subscribe to bot events**, add:
   - `message.channels` — Messages in public channels
   - `message.groups` — Messages in private channels
   - `message.im` — Direct messages (for secure `!auth` via DM)

### Install to Workspace
1. Go to **Install App**
2. Click **Install to Workspace**
3. Copy the **Bot User OAuth Token** (starts with `xoxb-`)

### Optional: User Token (for Search)
If you need the `slack_search` tool:
1. Go to **OAuth & Permissions** (same page where you added Bot Token Scopes)
2. Scroll down past the "Bot Token Scopes" section to find **User Token Scopes**
3. Click **Add an OAuth Scope** under User Token Scopes and add: `search:read`
4. Go to **Install App** and click **Reinstall to Workspace** (required after adding scopes)
5. After reinstalling, the page will show both tokens — copy the **User OAuth Token** (starts with `xoxp-`)

## Step 2: Install the Plugin

```bash
# From your dev machine:
docker cp a0-slack/ <container>:/tmp/a0-slack/
docker exec <container> bash -c "cd /tmp/a0-slack && ./install.sh"
docker exec <container> supervisorctl restart run_ui
```

Or via install script:
```bash
./install.sh
```

## Step 3: Configure

1. Open Agent Zero WebUI
2. Go to **Settings > External Services > Slack Integration**
3. Enter your **Bot Token** (xoxb-)
4. Enter your **App-Level Token** (xapp-)
5. Click **Save Slack Settings**
6. Click **Test Connection** on the dashboard

## Step 4: Try It

Ask the agent:
- "List my Slack channels"
- "Read the last 10 messages from #general"
- "Send 'Hello from Agent Zero!' to channel C01ABC23DEF"
- "Summarize the conversation in #project-updates"

## Chat Bridge Setup

To chat with Agent Zero directly from Slack:
1. "Add Slack channel C01ABC23DEF to the chat bridge"
2. "Start the Slack chat bridge"
3. Now type messages in that Slack channel — Agent Zero will respond!

### Elevated Mode (Optional)
To use elevated mode (full Agent Zero access from Slack):
1. Enable elevated mode in plugin settings
2. Send `!auth <key>` as a **direct message** to the bot (not in the channel)
3. Your elevation applies to all bridge channels
4. Send `!deauth` to end the session

## Troubleshooting

- **"No token configured"**: Ensure you've saved tokens in the Settings panel
- **"not_authed"**: Check that the bot token is valid and hasn't been revoked
- **"missing_scope"**: Add the required scope in your Slack app settings and reinstall
- **Chat bridge not connecting**: Ensure the App-Level Token (xapp-) is configured for Socket Mode
