---
name: "slack-search"
description: "Search messages and files across a Slack workspace."
version: "1.0.0"
author: "AgentZero Slack Plugin"
license: "MIT"
tags: ["slack", "search", "find"]
triggers:
  - "search slack"
  - "find in slack"
  - "slack search"
allowed_tools:
  - slack_search
metadata:
  complexity: "basic"
  category: "research"
---

# Slack Search Skill

Search messages and files across a Slack workspace. Requires a user token (xoxp-).

## Workflow

### Search Messages
```json
{"tool": "slack_search", "args": {"action": "messages", "query": "deployment update"}}
```

### Search Files
```json
{"tool": "slack_search", "args": {"action": "files", "query": "design mockup"}}
```

## Tips
- Search supports Slack's search modifiers: `from:@user`, `in:#channel`, `before:2024-01-01`
- File search helps find shared documents, images, and code snippets
- Requires a user token (xoxp-) — bot tokens don't support search
