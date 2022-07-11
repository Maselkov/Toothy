import asyncio
import copy
import json
import logging
import traceback

import discord
import random
from discord.ext import commands

from toothy.toothy import DEBUG_GUILD

log = logging.getLogger(__name__)

STATUSES = {
    "online": discord.Status.online,
    "idle": discord.Status.idle,
    "dnd": discord.Status.dnd,
    "invisible": discord.Status.invisible
}

ACTIVITY_TYPES = {
    "listening": discord.ActivityType.listening,
    "watching": discord.ActivityType.watching,
    "playing": discord.ActivityType.playing,
    "streaming": discord.ActivityType.streaming
}


class Owner(commands.Cog):
    """Control the bot's global settings"""

    def __init__(self, bot):
        self.bot = bot
        self.presence_manager_current_index = 0

    async def cog_check(self, ctx):
        return await self.bot.is_owner(ctx.author)

    @commands.command(name="load")
    async def load_extension(self, ctx, *, name: str):
        """Loads an extension"""
        extension = "cogs." + name.strip()
        try:
            await self.bot.load_extension(extension)
        except Exception:
            return await ctx.send("```py\n{}\n```".format(
                traceback.format_exc()))
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
            await self.bot.unload_extension(extension)
        except Exception:
            return await ctx.send("```py\n{}\n```".format(
                traceback.format_exc()))
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
            await self.bot.reload_extension(extension)
        except Exception:
            return await ctx.send("```py\n{}\n```".format(
                traceback.format_exc()))
        await ctx.send("Extension reloaded succesfully")

    @commands.command()
    async def doas(self, ctx, member: discord.Member, *, command):
        """Do a command as if another member had done it"""
        message = copy.copy(ctx.message)
        message.content = ctx.prefix + command
        message.author = member
        await self.bot.process_commands(message)

    @commands.command()
    async def sync(self, ctx, guild_only: bool = False):
        """Sync command tree. TODO: Automatic!"""
        if guild_only:
            test_guild = discord.Object(id=self.bot.test_guild)
            self.bot.tree.copy_global_to(guild=test_guild)
            await self.bot.tree.sync(guild=test_guild)
        else:
            await self.bot.tree.sync()
        await ctx.send("Synced")

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
    async def presence_mgr_interval(self,
                                    ctx,
                                    interval: int,
                                    maximum: int = 0):
        """Interval at which game will be changed, in seconds

        If you provide 2 intervals, the interval will be randomly chosen
        between them
        """
        if not maximum:
            await self.bot.database.set_cog_config(
                self, {
                    "presence.interval": interval,
                    "presence.interval_range": None
                })
            return await ctx.send("Interval set to {} seconds".format(
                str(interval)))
        await self.bot.database.set_cog_config(
            self, {
                "presence.interval": None,
                "presence.interval_range": [interval, maximum]
            })
        await ctx.send("Interval set to range between {} and {}".format(
            interval, maximum))

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

    @manager.command(name="type")
    async def presence_mgr_type(self, ctx, activity_type):
        """Sets type for presence manager

        Possible values: playing, listening, watching
        """
        activity_type = activity_type.lower()
        if activity_type not in ACTIVITY_TYPES:
            return await self.bot.send_cmd_help(ctx)
        await self.bot.database.set_cog_config(
            self, {"presence.type": activity_type})
        await ctx.send("Activity type changed")

    @manager.command(name="randomize")
    async def presence_mgr_randomize(self, ctx, yes_no: bool):
        """Sets whether to randomize status"""
        await self.bot.database.set_cog_config(self,
                                               {"presence.randomize": yes_no})
        await ctx.send("Toggled randomization")

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
            except IndexError:
                return await self.bot.send_cmd_help(ctx)
        else:
            try:
                game = discord.Game(name=args[0])
            except IndexError:
                return await self.bot.send_cmd_help(ctx)
        await self.bot.change_presence(activity=game,
                                       status=current_presence["status"])
        await ctx.send("Done.")

    @presence.command(name="status")
    async def presence_status(self, ctx, status):
        """Sets presence. Will be overriden by presence manager if active."""
        status = status.lower()
        current_presence = self.get_current_presence(ctx)
        if status not in STATUSES:
            await self.bot.send_cmd_help(ctx)
            return
        await self.bot.change_presence(status=STATUSES[status],
                                       activity=current_presence["game"])
        await ctx.send("Status changed.")

    @commands.command()
    async def toggleprivileged(self, ctx, user: discord.User):
        """Toggles user's privileged status.

        Privileged users can bypass command cooldowns."""
        status = not await self.bot.database.get_flag(ctx.author, "vip")
        await self.bot.database.set_flag(ctx.author, vip=status)
        if status:
            return await ctx.send("User is now privileged")
        return await ctx.send("User is no longer privileged")

    def get_current_presence(self, ctx):
        guild = ctx.guild
        if guild is None:
            return {"game": None, "status": None}
        return {"game": guild.me.activity, "status": guild.me.status}

    async def presence_manager(self):
        while self is self.bot.get_cog("Global"):
            try:
                doc = await self.bot.database.get_cog_config(self)
                if not doc:
                    await asyncio.sleep(10)
                    continue
                settings = doc["presence"]
                if settings["enabled"]:
                    games = settings.get("games", [])
                    status = STATUSES[settings["status"]]
                    activity_type = ACTIVITY_TYPES[settings["type"]]
                    randomize = settings.get("randomize", False)
                    interval = settings.get("interval")
                    if not interval:
                        interval_range = settings.get("interval_range")
                        if interval_range:
                            interval = random.randrange(*interval_range)
                    if not interval and not interval_range:
                        await asyncio.sleep(10)
                        continue
                    if self.bot.available:
                        if not games:
                            game = None
                        elif randomize:
                            game = random.choice(games)
                        else:
                            try:
                                game = games[
                                    self.presence_manager_current_index]
                                self.presence_manager_current_index += 1
                            except IndexError:
                                self.presence_manager_current_index = 0
                                game = games[0]
                        activity = discord.Activity(
                            name=game.format(bot=self.bot), type=activity_type)
                        await self.bot.change_presence(activity=activity,
                                                       status=status)
                    await asyncio.sleep(interval)
            except Exception as e:
                log.exception(e)
                await asyncio.sleep(300)
                continue


async def setup(bot):
    cog = Owner(bot)
    loop = bot.loop
    loop.create_task(
        bot.database.setup_cog(
            cog, {
                "presence": {
                    "interval": 180,
                    "interval_range": [],
                    "status": "online",
                    "type": "playing",
                    "enabled": False,
                    "randomize": False,
                    "games": []
                }
            }))
    loop.create_task(cog.presence_manager())
    await bot.add_cog(cog)
