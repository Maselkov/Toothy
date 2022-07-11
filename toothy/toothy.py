import datetime
import json
import logging
import sys

import aiohttp
import discord
from discord.ext import commands

from .database import MongoController

log = logging.getLogger(__name__)

try:
    with open("settings/config.json", encoding="utf-8", mode="r") as f:
        data = json.load(f)
        TOKEN = data["TOKEN"]
        DESCRIPTION = data["DESCRIPTION"]
        OWNER_ID = data["OWNER_ID"]
        DB_SETTINGS = data["DATABASE"]
        CASE_INSENSITIVE = data["CASE_INSENSITIVE_COMMANDS"]
        COLOR = int(data["COLOR"], 16)
        INTENTS = discord.Intents(**data["INTENTS"])
        TEST_GUILD = data["TEST_GUILD"]
        DEBUG = data.get("DEBUG", False)
except Exception:
    print("Config.json is not valid. Make sure you copied the example "
          "and renamed it.")
    sys.exit(1)

if not TOKEN:
    print("Token not set in config.json")
    sys.exit(1)


class Toothy(commands.AutoShardedBot):

    def __init__(self):

        def prefix_callable(bot, message):
            prefix = self.global_prefixes
            return prefix + [
                "<@!{.user.id}> ".format(self), self.user.mention + " "
            ]

        super().__init__(
            command_prefix=prefix_callable,
            description=DESCRIPTION,
            owner_id=OWNER_ID,
            case_insensitive=CASE_INSENSITIVE,
            intents=INTENTS,
        )
        self.database = MongoController(self, DB_SETTINGS)
        self.available = True
        self.global_prefixes = data["PREFIXES"]
        self.uptime = datetime.datetime.utcnow()
        self.color = discord.Color(COLOR)
        self.session = None
        self.test_guild = TEST_GUILD
        self.uptime = datetime.datetime.utcnow()

    async def setup_hook(self):
        self.session = aiohttp.ClientSession(loop=self.loop)
        try:
            with open("settings/extensions.json", encoding="utf-8",
                      mode="r") as f:
                extensions = json.load(f)
        except Exception:
            extensions = {"owner": True}
        for name, state in extensions.items():
            if state:
                try:
                    await self.load_extension(name)
                except Exception as e:
                    log.exception("Failed to load {}".format(name), exc_info=e)
                    state = False
        owner_cog = self.get_cog("Owner")
        if not owner_cog:
            print("Owner cog not loaded, exiting")
            sys.exit(1)
        with open("settings/extensions.json", encoding="utf-8", mode="w") as f:
            f.write(json.dumps(extensions, indent=4, sort_keys=True))

    async def on_ready(self):
        print("Toothy ready")
        print("Serving {} guilds".format(len(self.guilds)))

    async def on_message(self, message):
        user = message.author
        if user.bot:
            return
        if user.id != self.owner_id:
            return
        await self.process_commands(message)

    async def on_command_error(self, ctx, exc):
        if isinstance(exc, commands.NoPrivateMessage):
            await ctx.send("This command cannot be used in DMs")
            ctx.command.reset_cooldown(ctx)
        elif isinstance(exc, commands.CommandOnCooldown):
            if await ctx.bot.database.get_flag(ctx.author, "vip"):
                await ctx.reinvoke()
            else:
                await ctx.send(
                    "You cannot use this command again for the next "
                    "{:.2f} seconds"
                    "".format(exc.retry_after))
        elif isinstance(
                exc, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send_help(ctx.command)
            ctx.command.reset_cooldown(ctx)
        elif isinstance(exc, commands.DisabledCommand):
            await ctx.send("This command is disabled")
        elif isinstance(exc, commands.CommandInvokeError):
            message = ("Something went wrong. If the issue persists, please "
                       "contact the author. ")
            await ctx.send(message)
            log.exception(
                "Exception in command " + ctx.command.qualified_name,
                exc_info=exc.original,
            )
        elif isinstance(exc, commands.MissingPermissions):
            missing = [
                p.replace("guild", "server").replace("_", " ").title()
                for p in exc.missing_perms
            ]
            await ctx.send(
                "You're missing the following permissions to use this "
                "command: `{}`".format(", ".join(missing)))
        elif isinstance(exc, commands.BotMissingPermissions):
            missing = [
                p.replace("guild", "server").replace("_", " ").title()
                for p in exc.missing_perms
            ]
            await ctx.send(
                "The bot is missing the following permissions to be able to "
                "run this command:\n`{}`\nPlease add them then try again".
                format(", ".join(missing)))
        elif isinstance(exc, commands.CommandNotFound):
            pass
        elif isinstance(exc, commands.CheckFailure):
            pass

    async def close(self):
        await super().close()
        if self.session:
            await self.session.close()

    def save_config(self):
        with open("settings/config.json", encoding="utf-8", mode="r") as f:
            data = json.load(f)
        data["DESCRIPTION"] = (DESCRIPTION, )
        data["PREFIXES"] = self.global_prefixes
        with open("settings/config.json", encoding="utf-8", mode="w") as f:
            f.write(json.dumps(data, indent=4, sort_keys=True))

    async def start(self):
        await super().start(TOKEN)
