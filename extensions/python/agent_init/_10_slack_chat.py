"""Auto-start the Slack chat bridge on agent initialization.

Only starts if:
  - A bot token is configured
  - An app token is configured (Socket Mode)
  - chat_bridge.auto_start is true in config
  - At least one chat channel is registered
"""

import asyncio
import logging

logger = logging.getLogger("slack_chat_bridge")


async def execute(agent, **kwargs):
    try:
        from helpers import plugins

        config = plugins.get_plugin_config("slack", agent=agent)
        bot_token = config.get("bot", {}).get("token", "")
        app_token = config.get("bot", {}).get("app_token", "")

        if not bot_token:
            return  # No token, skip

        if not app_token:
            return  # No app token, Socket Mode requires it

        bridge_config = config.get("chat_bridge", {})
        if not bridge_config.get("auto_start", False):
            return  # Auto-start disabled

        from usr.plugins.slack.helpers.slack_bot import get_chat_channels, start_chat_bridge

        channels = get_chat_channels()
        if not channels:
            return  # No channels configured

        logger.info(f"Auto-starting Slack chat bridge ({len(channels)} channel(s))...")
        await start_chat_bridge(bot_token, app_token)
        logger.info("Slack chat bridge auto-started successfully.")

    except Exception as e:
        logger.warning(f"Slack chat bridge auto-start failed: {e}")
