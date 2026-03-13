from helpers.tool import Tool, Response
from plugins.slack.helpers.slack_client import (
    SlackClient, get_slack_config, get_modes_to_try,
)
from plugins.slack.helpers.sanitize import require_auth, sanitize_username, validate_slack_id
from slack_sdk.errors import SlackApiError


class SlackMembers(Tool):
    """List workspace or channel members in Slack."""

    async def execute(self, **kwargs) -> Response:
        action = self.args.get("action", "list")
        channel_id = self.args.get("channel_id", "")
        user_id = self.args.get("user_id", "")

        # Validate IDs when provided
        try:
            if channel_id:
                channel_id = validate_slack_id(channel_id, "channel_id")
            if user_id:
                user_id = validate_slack_id(user_id, "user_id")
        except ValueError as e:
            return Response(message=str(e), break_loop=False)

        config = get_slack_config(self.agent)
        try:
            require_auth(config)
        except ValueError as e:
            return Response(message=f"Auth error: {e}", break_loop=False)

        try:
            if action == "list":
                return await self._list_members(channel_id)
            elif action == "workspace":
                return await self._list_workspace()
            elif action == "info":
                return await self._user_info(user_id)
            else:
                return Response(
                    message=f"Unknown action '{action}'. Use: list, workspace, info.",
                    break_loop=False,
                )
        except SlackApiError as e:
            return Response(message=f"Slack API error: {e.response['error']}", break_loop=False)
        except Exception as e:
            return Response(message=f"Error: {e}", break_loop=False)

    async def _list_members(self, channel_id: str) -> Response:
        """List members in a specific channel."""
        if not channel_id:
            return Response(message="Error: channel_id is required.", break_loop=False)

        client = SlackClient.from_config(agent=self.agent, mode="bot")
        member_ids = await client.list_members(channel_id)

        if not member_ids:
            return Response(message="No members found or insufficient permissions.", break_loop=False)

        # Resolve user IDs to names (batch)
        lines = [f"Members of channel {channel_id} ({len(member_ids)} total):"]
        for uid in member_ids[:100]:  # Limit to 100
            try:
                user_data = await client.get_user_info(uid)
                profile = user_data.get("profile", {})
                display = sanitize_username(
                    profile.get("display_name") or profile.get("real_name") or uid
                )
                username = sanitize_username(user_data.get("name", uid))
                bot_tag = " [BOT]" if user_data.get("is_bot") else ""
                admin_tag = " [ADMIN]" if user_data.get("is_admin") else ""
                lines.append(f"  - {display} (@{username}, ID: {uid}){bot_tag}{admin_tag}")
            except Exception:
                lines.append(f"  - {uid}")

        await client.close()
        return Response(message="\n".join(lines), break_loop=False)

    async def _list_workspace(self) -> Response:
        """List all workspace members."""
        client = SlackClient.from_config(agent=self.agent, mode="bot")
        data = await client.list_workspace_members(limit=200)
        members = data.get("members", [])

        if not members:
            return Response(message="No workspace members found.", break_loop=False)

        # Filter out bots and deactivated users
        active = [m for m in members if not m.get("deleted")]
        humans = [m for m in active if not m.get("is_bot")]
        bots = [m for m in active if m.get("is_bot")]

        lines = [f"Workspace members ({len(humans)} humans, {len(bots)} bots):"]
        for m in humans:
            profile = m.get("profile", {})
            display = sanitize_username(
                profile.get("display_name") or profile.get("real_name") or m.get("name", "?")
            )
            username = sanitize_username(m.get("name", "?"))
            admin_tag = " [ADMIN]" if m.get("is_admin") else ""
            owner_tag = " [OWNER]" if m.get("is_owner") else ""
            lines.append(f"  - {display} (@{username}, ID: {m['id']}){admin_tag}{owner_tag}")

        if bots:
            lines.append(f"\nBots ({len(bots)}):")
            for b in bots[:20]:
                profile = b.get("profile", {})
                display = sanitize_username(
                    profile.get("display_name") or profile.get("real_name") or b.get("name", "?")
                )
                lines.append(f"  - {display} (ID: {b['id']})")

        await client.close()
        return Response(message="\n".join(lines), break_loop=False)

    async def _user_info(self, user_id: str) -> Response:
        """Get detailed info about a specific user."""
        if not user_id:
            return Response(message="Error: user_id is required.", break_loop=False)

        client = SlackClient.from_config(agent=self.agent, mode="bot")
        user_data = await client.get_user_info(user_id)
        await client.close()

        if not user_data:
            return Response(message=f"User {user_id} not found.", break_loop=False)

        profile = user_data.get("profile", {})
        display = sanitize_username(
            profile.get("display_name") or profile.get("real_name") or user_id
        )
        username = sanitize_username(user_data.get("name", user_id))

        lines = [
            f"Slack User Profile:",
            f"  Username: @{username}",
            f"  Display Name: {display}",
            f"  User ID: {user_id}",
            f"  Title: {profile.get('title', 'N/A')}",
            f"  Email: {profile.get('email', 'N/A')}",
            f"  Bot: {'Yes' if user_data.get('is_bot') else 'No'}",
            f"  Admin: {'Yes' if user_data.get('is_admin') else 'No'}",
            f"  Status: {profile.get('status_text', '') or 'N/A'}",
            f"  Timezone: {user_data.get('tz_label', 'N/A')}",
        ]
        return Response(message="\n".join(lines), break_loop=False)
