---
name: "slack-communicate"
description: "Send messages, reactions, and file uploads to Slack channels."
version: "1.0.0"
author: "AgentZero Slack Plugin"
license: "MIT"
tags: ["slack", "send", "messaging"]
triggers:
  - "send slack message"
  - "post to slack"
  - "slack react"
  - "upload to slack"
allowed_tools:
  - slack_send
  - slack_read
metadata:
  complexity: "basic"
  category: "communication"
---

# Slack Communication Skill

Send messages, reactions, and upload files to Slack channels.

## Workflow

### Step 1: Identify the Channel
If the channel ID is not known, list channels first:
```json
{"tool": "slack_read", "args": {"action": "channels"}}
```

### Step 2: Send a Message
```json
{"tool": "slack_send", "args": {"action": "send", "channel_id": "C01ABC23DEF", "content": "Hello team!"}}
```

### Reply in Thread
```json
{"tool": "slack_send", "args": {"action": "send", "channel_id": "C01ABC23DEF", "content": "Great point.", "thread_ts": "1234567890.123456"}}
```

### React to a Message
```json
{"tool": "slack_send", "args": {"action": "react", "channel_id": "C01ABC23DEF", "timestamp": "1234567890.123456", "emoji": "thumbsup"}}
```

### Upload a File
```json
{"tool": "slack_send", "args": {"action": "upload", "channel_id": "C01ABC23DEF", "content": "report data", "filename": "report.txt"}}
```

## Tips
- Long messages are automatically split into 4000-char chunks
- Use thread_ts to reply in threads instead of the main channel
- Emoji names don't need colons (use "thumbsup" not ":thumbsup:")
