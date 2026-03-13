---
name: "slack-research"
description: "Summarize Slack channel conversations to extract key topics, decisions, and action items."
version: "1.0.0"
author: "AgentZero Slack Plugin"
license: "MIT"
tags: ["slack", "summarize", "research", "analysis"]
triggers:
  - "summarize slack"
  - "slack summary"
  - "what happened in slack"
  - "slack channel recap"
allowed_tools:
  - slack_summarize
  - slack_read
metadata:
  complexity: "intermediate"
  category: "research"
---

# Slack Research Skill

Summarize Slack conversations to extract key topics, decisions, and action items.

## Workflow

### Step 1: Identify the Channel
```json
{"tool": "slack_read", "args": {"action": "channels"}}
```

### Step 2: Summarize
```json
{"tool": "slack_summarize", "args": {"channel_id": "C01ABC23DEF", "limit": "100"}}
```

### Summarize a Thread
```json
{"tool": "slack_summarize", "args": {"channel_id": "C01ABC23DEF", "thread_ts": "1234567890.123456"}}
```

## Tips
- Summaries are auto-saved to memory by default (set save_to_memory=false to disable)
- Increase the limit for longer time ranges (up to 500)
- Thread summaries are great for focused discussions
