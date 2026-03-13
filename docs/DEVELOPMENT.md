# Slack Plugin — Development Guide

## Project Structure

```
a0-slack/
├── plugin.yaml              # Plugin manifest (name must be "slack")
├── default_config.yaml      # Default settings
├── initialize.py            # Dependency installer (slack-sdk, aiohttp, pyyaml)
├── install.sh               # Deployment script
├── helpers/
│   ├── __init__.py
│   ├── slack_client.py      # Slack Web API wrapper using slack-sdk
│   ├── slack_bot.py         # Chat bridge via Socket Mode
│   └── sanitize.py          # Prompt injection defense (shared with all tools)
├── tools/                   # 7 tool implementations
│   ├── slack_read.py        # Read messages, list channels, threads
│   ├── slack_send.py        # Send messages, reactions, file uploads
│   ├── slack_members.py     # List workspace/channel members
│   ├── slack_summarize.py   # LLM-powered conversation summaries
│   ├── slack_search.py      # Search messages/files (user token)
│   ├── slack_manage.py      # Pin, topic, archive management
│   └── slack_chat.py        # Chat bridge lifecycle management
├── prompts/                 # Tool prompt definitions for LLM context
├── api/                     # WebUI API handlers (all CSRF-protected)
│   ├── slack_config_api.py  # Config get/set/auth-key
│   ├── slack_bridge_api.py  # Bridge start/stop/status
│   └── slack_test.py        # Connection test
├── webui/
│   ├── main.html            # Dashboard (status, bridge controls)
│   └── config.html          # Settings (tokens, bridge, elevated mode)
├── extensions/
│   └── python/agent_init/
│       └── _10_slack_chat.py # Auto-start bridge on agent init
├── skills/                  # 5 user-facing skills
├── tests/
│   └── regression_test.sh   # 58+ tests across 12 categories
└── docs/
```

## Development Setup

1. Start the dev container:
   ```bash
   docker start agent-zero-dev-latest
   ```

2. Install the plugin:
   ```bash
   docker cp a0-slack/. agent-zero-dev-latest:/a0/usr/plugins/slack/
   docker exec agent-zero-dev-latest ln -sf /a0/usr/plugins/slack /a0/plugins/slack
   docker exec agent-zero-dev-latest touch /a0/usr/plugins/slack/.toggle-1
   docker exec agent-zero-dev-latest supervisorctl restart run_ui
   ```

3. Run tests:
   ```bash
   ./tests/regression_test.sh agent-zero-dev-latest 50084
   ```

## Key Patterns

### Tool Pattern
All tools subclass `Tool`, implement `async execute()`, return `Response`:
```python
from helpers.tool import Tool, Response

class SlackFoo(Tool):
    async def execute(self, **kwargs) -> Response:
        action = self.args.get("action", "")
        config = get_slack_config(self.agent)
        # ... implementation ...
        return Response(message="result", break_loop=False)
```

### Config Access
```python
from plugins.slack.helpers.slack_client import get_slack_config
config = get_slack_config(self.agent)
```

### API Handler Pattern
```python
from helpers.api import ApiHandler, Request, Response

class SlackFooApi(ApiHandler):
    @classmethod
    def requires_csrf(cls) -> bool:
        return True  # MANDATORY — never return False
```

### WebUI Pattern
```javascript
const fetchApi = globalThis.fetchApi || fetch;  // CSRF-aware
// Use data-sl="name" attributes for scoped lookups, not bare IDs
```

### Security
- All external content goes through `sanitize.py` before LLM context
- CSRF on every API handler (never `return False`)
- Token masking in config API responses
- Atomic file writes with 0o600 permissions
- HMAC constant-time comparison for auth keys

## Adding a New Tool

1. Create `tools/slack_<name>.py` with a `Tool` subclass
2. Create `prompts/agent.system.tool.slack_<name>.md` (JSON examples, security notes)
3. Import sanitization helpers for all external data
4. Add tests in `tests/regression_test.sh` (tool import + functional tests)
5. Update README.md tool table
