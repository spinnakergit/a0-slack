"""API endpoint: Test Slack connection.
URL: POST /api/plugins/slack/slack_test
"""
from helpers.api import ApiHandler, Request, Response


class SlackTest(ApiHandler):

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]

    @classmethod
    def requires_csrf(cls) -> bool:
        return True

    async def process(self, input: dict, request: Request) -> dict | Response:
        try:
            from usr.plugins.slack.helpers.slack_client import SlackClient, get_slack_config

            config = get_slack_config()
            has_bot = bool((config.get("bot", {}).get("token", "") or "").strip())
            has_user = bool((config.get("user", {}).get("token", "") or "").strip())

            if not has_bot and not has_user:
                return {"ok": False, "error": "No token configured. Add a Bot Token (xoxb-) in plugin settings."}
            if not has_bot:
                return {"ok": False, "error": "No bot token configured. The bot token (xoxb-) is required for most operations."}

            client = SlackClient.from_config(mode="bot")
            auth = await client.auth_test()
            await client.close()

            result = {
                "ok": True,
                "user": auth.get("user", "Unknown"),
                "mode": "bot",
                "user_id": auth.get("user_id"),
                "team": auth.get("team", "Unknown"),
                "team_id": auth.get("team_id"),
            }
            if has_user:
                result["user_token"] = True
            return result
        except Exception as e:
            return {"ok": False, "error": f"Connection failed: {type(e).__name__}"}
