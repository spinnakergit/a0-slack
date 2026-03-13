# Slack Plugin Documentation

## Overview

Read, send, and manage messages in Slack workspaces with real-time chat bridge support via Socket Mode.

## Contents

- [Quick Start](QUICKSTART.md) — Installation and first-use guide
- [Development](DEVELOPMENT.md) — Contributing and development setup

## Tools

| Tool | Description |
|------|-------------|
| `slack_read` | Read messages, list channels, list thread replies |
| `slack_send` | Send messages, reactions, file uploads |
| `slack_members` | List workspace/channel members, get user profiles |
| `slack_summarize` | Summarize channel/thread history using LLM |
| `slack_search` | Search messages/files across workspace |
| `slack_manage` | Pin/unpin, set topic/purpose, archive channels |
| `slack_chat` | Chat bridge control (start/stop, add/remove channels) |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/plugins/slack/slack_test` | POST | Test connection |
| `/api/plugins/slack/slack_config_api` | GET/POST | Read/write config, generate auth key |
| `/api/plugins/slack/slack_bridge_api` | POST | Bridge start/stop/restart/status |

## Auth Model

- **Bot Token (xoxb-)**: Primary access for reading/sending messages
- **App-Level Token (xapp-)**: Required for Socket Mode (chat bridge)
- **User Token (xoxp-)**: Optional, enables search functionality
