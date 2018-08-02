import asyncio
import copy
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

ACTIVITY_TYPES = {
    "listening": discord.ActivityType.listening,
    "watching": discord.ActivityType.watching,
    "playing": discord.ActivityType.playing,
    "streaming": discord.ActivityType.streaming
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
            return await ctx.send("```py\n{}\n```".format(
                traceback.format_exc()))
        with open("settings/extensions.json", encoding="utf-8", mode="r") as f:
            data = json.load(f)
            data[extension] = True
        with open("settings/extensions.json", encoding="utf-8", mode="w") as f:
            f.write(json.dumps(data, indent=4, sort_keys=True))
        await ctx.send("Extension loaded succesfully")
        await self.bot.disable_commands(self)

    @commands.command(name="unload")
    async def unload_extension(self, ctx, *, name: str):
        """Unloads an extension"""
        extension = "cogs." + name.strip()
        if extension == "cogs.global":
            return await ctx.send("Can't unload global cog")
        try:
            self.bot.unload_extension(extension)
        except Exception as e:
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
            self.bot.unload_extension(extension)
        except Exception as e:
            return await ctx.send("```py\n{}\n```".format(
                traceback.format_exc()))
        try:
            self.bot.load_extension(extension)
        except Exception as e:
            return await ctx.send("```py\n{}\n```".format(
                traceback.format_exc()))
        with open("settings/extensions.json", encoding="utf-8", mode="r") as f:
            data = json.load(f)
            data[extension] = True
        with open("settings/extensions.json", encoding="utf-8", mode="w") as f:
            f.write(json.dumps(data, indent=4, sort_keys=True))
        await ctx.send("Extension reloaded succesfully")
        await self.bot.disable_commands(self)

    @commands.command()
    async def doas(self, ctx, member: discord.Member, *, command):
        """Do a command as if another member had done it"""
        message = copy.copy(ctx.message)
        message.content = ctx.prefix + command
        message.author = member
        await self.bot.process_commands(message)

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
        await self.bot.change_presence(
            activity=game, status=current_presence["status"])
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
            status=STATUSES[status], activity=current_presence["game"])
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

    @commands.group(name="command")
    async def cmd_disable(self, ctx):
        """Disable/enable commands globally"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)

    @cmd_disable.command(name="disable")
    async def cmd_disable_off(self, ctx, *, cmd):
        """Globally disable a command"""
        cmd = cmd.lower()
        cmd_obj = self.bot.get_command(cmd)
        if not cmd_obj:
            return await ctx.send("Invalid command")
        if not cmd_obj.enabled:
            return await ctx.send("This command is already disabled")
        await self.bot.database.set_cog_config(
            self, {"disabled_commands": cmd}, operator="$push")
        self.bot.disable_command(cmd_obj)
        await ctx.send("`{}` disabled".format(cmd_obj.name))

    @cmd_disable.command(name="enable")
    async def cmd_disable_on(self, ctx, *, cmd):
        """Globally enable a command"""
        cmd = cmd.lower()
        cmd_obj = self.bot.get_command(cmd)
        if not cmd_obj:
            return await ctx.send("Invalid command")
        if cmd_obj.enabled:
            return await ctx.send("This command is already enabled")
        await self.bot.database.set_cog_config(
            self, {"disabled_commands": cmd}, operator="$pull")
        cmd_obj.enabled = True
        cmd_obj.hidden = False
        await ctx.send("`{}` enabled".format(cmd_obj.name))

    @cmd_disable.command(name="list")
    async def cmd_disable_list(self, ctx):
        """List disabled commands"""
        commands = "\n".join(await self.bot.get_disabled_commands(self))
        if not commands:
            return await ctx.send("There are currently no disabled commands")
        await ctx.send("Disabled commands are:```\n{}\n```".format(commands))

    @commands.command()
    async def toggleprivileged(self, ctx, user: discord.User):
        """Toggles user's privileged status.

        Privileged users can bypass command cooldowns."""
        status = not await self.bot.user_is_privileged(user)
        await self.bot.database.set_user(user, {"vip": status})
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
                    status = STATUSES[settings["status"]]
                    activity_type = ACTIVITY_TYPES[settings["type"]]
                    games = settings["games"] if settings["games"] else [None]
                    for game in games:
                        if self.bot.available:
                            activity = discord.Activity(
                                name=game.format(bot=self.bot),
                                type=activity_type)
                            await self.bot.change_presence(
                                activity=activity, status=status)
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
        bot.database.setup_cog(
            cog, {
                "presence": {
                    "interval": 180,
                    "status": "online",
                    "type": "playing",
                    "enabled": False,
                    "games": []
                },
                "disabled_commands": []
            }))
    loop.create_task(cog.presence_manager())
    bot.add_cog(cog)
