import asyncio
import json
import logging
import traceback

import discord
from discord.ext import commands

log = logging.getLogger(__name__)

STATUSES = {
    "online": discord.Status.online,
    "idle": discord.Status.idle,
    "dnd": discord.Status.dnd,
    "invisible": discord.Status.invisible
}


class Global:
    """Control the bot's global settings"""

    def __init__(self, bot):
        self.bot = bot

    async def __local_check(self, ctx):
        return await self.bot.is_owner(ctx.author)

    @commands.command(name="load")
    async def load_extension(self, ctx, *, name: str):
        """Loads an extension"""
        extension = "cogs." + name.strip()
        try:
            self.bot.load_extension(extension)
        except Exception as e:
            return await ctx.send(
                "```py\n{}\n```".format(traceback.format_exc()))
        with open("settings/extensions.json", encoding="utf-8", mode="r") as f:
            data = json.load(f)
            data[extension] = True
        with open("settings/extensions.json", encoding="utf-8", mode="w") as f:
            f.write(json.dumps(data, indent=4, sort_keys=True))
        await ctx.send("Extension loaded succesfully")

    @commands.command(name="unload")
    async def unload_extension(self, ctx, *, name: str):
        """Unloads an extension"""
        extension = "cogs." + name.strip()
        if extension == "cogs.global":
            return await ctx.send("Can't unload global cog")
        try:
            self.bot.unload_extension(extension)
        except Exception as e:
            return await ctx.send(
                "```py\n{}\n```".format(traceback.format_exc()))
        with open("settings/extensions.json", encoding="utf-8", mode="r") as f:
            data = json.load(f)
            data[extension] = False
        with open("settings/extensions.json", encoding="utf-8", mode="w") as f:
            f.write(json.dumps(data, indent=4, sort_keys=True))
        await ctx.send("Extension unloaded succesfully")

    @commands.command(name="reload")
    async def reload_extension(self, ctx, *, name: str):
        """Reloads an extension"""
        extension = "cogs." + name.strip()
        try:
            self.bot.unload_extension(extension)
        except Exception as e:
            return await ctx.send(
                "```py\n{}\n```".format(traceback.format_exc()))
        try:
            self.bot.load_extension(extension)
        except Exception as e:
            return await ctx.send(
                "```py\n{}\n```".format(traceback.format_exc()))
        with open("settings/extensions.json", encoding="utf-8", mode="r") as f:
            data = json.load(f)
            data[extension] = True
        with open("settings/extensions.json", encoding="utf-8", mode="w") as f:
            f.write(json.dumps(data, indent=4, sort_keys=True))
        await ctx.send("Extension reloaded succesfully")

    @commands.group()
    async def presence(self, ctx):
        """Commands for presence management"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)
            return

    @presence.group()
    async def manager(self, ctx):
        """Commands for presence manager"""
        if ctx.invoked_subcommand is None or isinstance(
                ctx.invoked_subcommand, commands.Group):
            await self.bot.send_cmd_help(ctx)
            return

    @manager.command(name="interval")
    async def presence_mgr_interval(self, ctx, interval: int):
        """Interval at which game will be changed, in seconds"""
        await self.bot.database.set_cog_config(self,
                                               {"presence.interval": interval})
        await ctx.send("Interval set to {} seconds".format(str(interval)))

    @manager.command(name="games")
    async def presence_mgr_games(self, ctx, *games):
        """A list of games which will be rotated at interval.
        Separated by spaces, enclosed in double quotes"""
        await self.bot.database.set_cog_config(self,
                                               {"presence.games": list(games)})
        await ctx.send("Games set")

    @manager.command(name="toggle")
    async def presence_mgr_toggle(self, ctx, on_off: bool):
        """Enable or disable presence manager"""
        await self.bot.database.set_cog_config(self,
                                               {"presence.enabled": on_off})
        await ctx.send("Enabled")

    @manager.command(name="status")
    async def presence_mgr_status(self, ctx, status):
        """Sets status for presence manager"""
        status = status.lower()
        if status not in STATUSES:
            await self.bot.send_cmd_help(ctx)
            return
        await self.bot.database.set_cog_config(self,
                                               {"presence.status": status})
        await ctx.send("Status changed")

    @presence.command()
    async def set(self, ctx, mode, *args):
        """Sets presence. Will be overriden by presence manager if active.

        For first parameter, use either "game", "stream" or "none".
        If stream, the second parameter will be the name of streamer, and the
        last one stream title.
        For game, the last parameter will be the game to display
        """
        current_presence = self.get_current_presence(ctx)
        mode = mode.lower()
        if mode not in ["game", "stream", "none"]:
            await ctx.send("Invalid parameter for mode. Use either "
                           "`game`, `stream` or `none`")
            return
        if mode == "none":
            game = None
        elif mode == "stream":
            try:
                streamer = "https://www.twitch.tv/{}".format(args[0])
                game = discord.Game(type=1, url=streamer, name=args[1])
            except:
                return await self.bot.send_cmd_help(ctx)
        else:
            try:
                game = discord.Game(name=args[0])
            except:
                return await self.bot.send_cmd_help(ctx)
        await self.bot.change_presence(
            game=game, status=current_presence["status"])
        await ctx.send("Done.")

    @presence.command(name="status")
    async def presence_status(self, ctx, status):
        """Sets presence. Will be overriden by presence manager if active."""
        status = status.lower()
        current_presence = self.get_current_presence(ctx)
        if status not in STATUSES:
            await self.bot.send_cmd_help(ctx)
            return
        await self.bot.change_presence(
            status=STATUSES[status], game=current_presence["game"])
        await ctx.send("Status changed.")

    @commands.group()
    async def blacklist(self, ctx):
        """Blacklist management commands

        Blacklisted users will be unable to issue commands"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)

    @blacklist.command(name="add")
    async def blacklist_add(self, ctx, user: discord.Member):
        """Globally blacklist user from the bot"""
        if not await self.bot.user_is_ignored(user):
            await self.bot.database.set_user(user, {"blacklisted": True})
            await ctx.send("Added to blacklist")
        else:
            await ctx.send("User already on blacklist")

    @blacklist.command(name="remove")
    async def blacklist_remove(self, ctx, user: discord.Member):
        """Remove user from the global blacklist"""
        if await self.bot.user_is_ignored(user):
            await self.bot.database.set_user(user, {"blacklisted": False})
            await ctx.send("User unblacklisted")
        else:
            await ctx.send("User not on blacklist")

    def get_current_presence(self, ctx):
        guild = ctx.guild
        if guild is None:
            return {"game": None, "status": None}
        return {"game": guild.me.game, "status": guild.me.status}

    async def presence_manager(self):
        while self is self.bot.get_cog("Global"):
            try:
                doc = await self.bot.database.get_cog_config(self)
                if not doc:
                    await asyncio.sleep(10)
                    continue
                settings = doc["presence"]
                if settings["enabled"]:
                    status = STATUSES[settings["status"]]
                    games = settings["games"] if settings["games"] else [None]
                    for game in games:
                        if self.bot.available:
                            game = discord.Game(name=game)
                            await self.bot.change_presence(
                                game=game, status=status)
                        await asyncio.sleep(settings["interval"])
                else:
                    await asyncio.sleep(300)
            except Exception as e:
                log.exception(e)
                await asyncio.sleep(300)
                continue


def setup(bot):
    cog = Global(bot)
    loop = bot.loop
    loop.create_task(
        bot.database.setup_cog(cog, {
            "presence": {
                "interval": 180,
                "status": "online",
                "enabled": False,
                "games": []
            }
        }))
    loop.create_task(cog.presence_manager())
    bot.add_cog(cog)
