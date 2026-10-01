"""Discord bot (HANDOFF section 8.3): ``/status /screenshot /pause /resume
/stop``, restricted to one Discord user id.

``BotCommands`` is the testable core - plain dispatch, no network. The
``discord.py`` ``Client``/slash-command glue around it is thin on purpose
and isn't exercised by the test suite (it needs a real gateway connection
and bot token); everything that can go wrong without one already lives in
``BotCommands``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

log = logging.getLogger(__name__)

NOT_AUTHORIZED = "You're not authorized to control this Warden instance."
UNKNOWN_COMMAND = "Unknown command."


class BotCommands:
    def __init__(
        self,
        allowed_user_id: str,
        get_status: Callable[[], str],
        on_pause: Callable[[], None],
        on_resume: Callable[[], None],
        on_stop: Callable[[], None],
        on_screenshot: Callable[[], str],
    ):
        self.allowed_user_id = str(allowed_user_id)
        self.get_status = get_status
        self.on_pause = on_pause
        self.on_resume = on_resume
        self.on_stop = on_stop
        self.on_screenshot = on_screenshot

    def is_authorized(self, user_id) -> bool:
        return bool(self.allowed_user_id) and str(user_id) == self.allowed_user_id

    def handle(self, command: str, user_id) -> str:
        if not self.is_authorized(user_id):
            log.warning("discord bot: unauthorized command '%s' from user %s", command, user_id)
            return NOT_AUTHORIZED
        handler = {
            "status": lambda: self.get_status(),
            "pause": lambda: (self.on_pause(), "Paused.")[1],
            "resume": lambda: (self.on_resume(), "Resumed.")[1],
            "stop": lambda: (self.on_stop(), "Stopped.")[1],
            "screenshot": lambda: self.on_screenshot(),
        }.get(command.lower().lstrip("/"))
        if handler is None:
            return UNKNOWN_COMMAND
        try:
            return handler()
        except Exception as exc:
            log.exception("discord bot command '%s' failed", command)
            return f"Command failed: {exc}"


class DiscordBotRunner:
    """Thin wrapper around ``discord.py``; only constructed/run when the
    bot is enabled and the dependency is actually installed.
    """

    def __init__(self, token: str, commands: BotCommands):
        self.token = token
        self.commands = commands
        self._client = None

    def available(self) -> bool:
        try:
            import discord  # noqa: F401
        except ImportError:
            return False
        return True

    def build_client(self):
        import discord
        from discord import app_commands

        intents = discord.Intents.default()
        client = discord.Client(intents=intents)
        tree = app_commands.CommandTree(client)

        for name in ("status", "pause", "resume", "stop", "screenshot"):
            def _make(cmd_name):
                async def _handler(interaction: "discord.Interaction"):
                    reply = self.commands.handle(cmd_name, interaction.user.id)
                    await interaction.response.send_message(reply, ephemeral=True)
                return _handler

            tree.command(name=name, description=f"Warden: {name}")(_make(name))

        @client.event
        async def on_ready():
            await tree.sync()
            log.info("discord bot ready as %s", client.user)

        self._client = client
        return client

    def run(self) -> None:
        client = self._client or self.build_client()
        client.run(self.token)
