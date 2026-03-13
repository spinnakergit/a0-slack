"""API endpoint: Chat bridge start/stop/status.
URL: POST /api/plugins/slack/slack_bridge_api
"""
from helpers.api import ApiHandler, Request, Response


class SlackBridgeApi(ApiHandler):

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    @classmethod
    def requires_csrf(cls) -> bool:
        return True

    async def process(self, input: dict, request: Request) -> dict | Response:
        action = input.get("action", "status")

        try:
            if action == "status":
                return self._status()
            elif action == "start":
                return await self._start()
            elif action == "stop":
                return await self._stop()
            elif action == "restart":
                return await self._restart()
            else:
                return {"ok": False, "error": f"Unknown action: {action}"}
        except Exception as e:
            return {"ok": False, "error": f"Bridge error: {type(e).__name__}"}

    def _status(self) -> dict:
        from plugins.slack.helpers.slack_bot import get_bot_status
        status = get_bot_status()
        return {"ok": True, **status}

    async def _start(self) -> dict:
        from plugins.slack.helpers.slack_bot import get_bot_status, start_chat_bridge
        from plugins.slack.helpers.slack_client import get_slack_config

        status = get_bot_status()
        if status.get("running"):
            return {"ok": True, "message": "Bridge is already running", **status}

        config = get_slack_config()
        token = (config.get("bot", {}).get("token", "") or "").strip()
        app_token = (config.get("bot", {}).get("app_token", "") or "").strip()
        if not token:
            return {"ok": False, "error": "No bot token configured"}
        if not app_token:
            return {"ok": False, "error": "No app token configured (required for Socket Mode)"}

        await start_chat_bridge(token, app_token)
        return {"ok": True, "message": "Bridge started", **get_bot_status()}

    async def _stop(self) -> dict:
        from plugins.slack.helpers.slack_bot import get_bot_status, stop_chat_bridge

        await stop_chat_bridge()
        return {"ok": True, "message": "Bridge stopped", **get_bot_status()}

    async def _restart(self) -> dict:
        from plugins.slack.helpers.slack_bot import get_bot_status, start_chat_bridge, stop_chat_bridge
        from plugins.slack.helpers.slack_client import get_slack_config

        await stop_chat_bridge()

        config = get_slack_config()
        token = (config.get("bot", {}).get("token", "") or "").strip()
        app_token = (config.get("bot", {}).get("app_token", "") or "").strip()
        if not token:
            return {"ok": False, "error": "No bot token configured"}
        if not app_token:
            return {"ok": False, "error": "No app token configured"}

        await start_chat_bridge(token, app_token)
        return {"ok": True, "message": "Bridge restarted", **get_bot_status()}
