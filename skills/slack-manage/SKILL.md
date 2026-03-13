---
name: "slack-manage"
description: "Manage Slack channels: pin messages, set topics, archive channels."
version: "1.0.0"
author: "AgentZero Slack Plugin"
license: "MIT"
tags: ["slack", "manage", "admin", "channels"]
triggers:
  - "manage slack channel"
  - "pin slack message"
  - "set slack topic"
  - "archive slack channel"
allowed_tools:
  - slack_manage
  - slack_read
metadata:
  complexity: "basic"
  category: "administration"
---

# Slack Channel Management Skill

Manage Slack channels: pin/unpin messages, set topics, and archive channels.

## Workflow

### Pin a Message
```json
{"tool": "slack_manage", "args": {"action": "pin", "channel_id": "C01ABC23DEF", "timestamp": "1234567890.123456"}}
```

### Set Channel Topic
```json
{"tool": "slack_manage", "args": {"action": "set_topic", "channel_id": "C01ABC23DEF", "topic": "Sprint 42 planning"}}
```

### List Pinned Items
```json
{"tool": "slack_manage", "args": {"action": "list_pins", "channel_id": "C01ABC23DEF"}}
```

### Archive a Channel
```json
{"tool": "slack_manage", "args": {"action": "archive", "channel_id": "C01ABC23DEF"}}
```

## Tips
- Read messages first to find the timestamp of the message to pin
- Archiving is reversible from the Slack UI but not via the API
- Bot needs to be a member of the channel to manage it
