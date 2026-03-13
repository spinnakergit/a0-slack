---
name: "slack-chat"
description: "Use Slack as a chat interface to Agent Zero's LLM. Set up a persistent bot that listens in designated channels via Socket Mode."
version: "1.0.0"
author: "AgentZero Slack Plugin"
license: "MIT"
tags: ["slack", "chat", "bridge", "llm"]
triggers:
  - "slack chat bridge"
  - "chat through slack"
  - "slack llm chat"
  - "talk to agent on slack"
allowed_tools:
  - slack_chat
  - slack_read
metadata:
  complexity: "intermediate"
  category: "communication"
---

# Slack Chat Bridge Skill

Set up Slack as a chat frontend to Agent Zero's LLM using Socket Mode.

## Setup Workflow

### Step 1: Find the Channel
List available channels:
```json
{"tool": "slack_read", "args": {"action": "channels"}}
```

### Step 2: Add the Channel
Designate the channel for LLM chat:
```json
{"tool": "slack_chat", "args": {"action": "add_channel", "channel_id": "C01ABC23DEF", "label": "llm-chat"}}
```

### Step 3: Start the Bot
Launch the chat bridge:
```json
{"tool": "slack_chat", "args": {"action": "start"}}
```

### Step 4: Verify
Check that the bot is connected:
```json
{"tool": "slack_chat", "args": {"action": "status"}}
```

## How It Works
- Uses Socket Mode (no public URL needed — works behind firewalls)
- Each designated channel gets its own conversation context
- Messages are prefixed with the sender's Slack display name
- Long responses are automatically split into 4000-char chunks
- Conversation history is maintained per channel across messages

## Tips
- Create a dedicated `#llm-chat` channel to keep things organized
- The bot only responds in channels you explicitly add
- Use `stop` and `start` to restart the bot if issues arise
- Enable `auto_start` in config to launch the bot automatically on agent startup
