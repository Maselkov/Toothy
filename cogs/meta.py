import time

import discord
from discord.ext import commands
from discord.ext.commands.cooldowns import BucketType


class Meta:
    """Commands related to the bot itself"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def ping(self, ctx):
        """Pong!"""
        start = time.time()
        e = discord.Embed(title="Pong! 🏓", color=0xdd2e44)
        e.add_field(
            name="Websocket latency",
            value=str(round(self.bot.latency * 1000)) + "ms")
        msg = await ctx.send(embed=e)
        e.add_field(
            name="HTTP latency",
            value=str(round((time.time() - start) * 1000)) + "ms")
        await msg.edit(embed=e)

    @commands.command()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def prefix(self, ctx, *prefixes):
        """Set the prefixes for this server, separated by space
        Invoke without prefixes to go back to default
        """
        guild = ctx.guild
        if not prefixes:
            await self.bot.database.set_guild(guild, {"prefixes": []})
            prefixes = ", ".join(self.bot.global_prefixes)
            await ctx.send(
                "Prefixes reset to default. Prefixes: `{}`".format(prefixes))
            return
        await self.bot.database.set_guild(guild, {"prefixes": prefixes})
        await ctx.send("Prefixes set. Prefixes: `{}`\nIn order to reset "
                       "prefixes to default, use the following command exactly"
                       " as shown"
                       "```{}prefix```".format(prefixes, prefixes[0]))

    async def on_guild_remove(self, guild):
        await self.bot.database.set_guild(guild, {"prefixes": []})

    @commands.group()
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def botnews(self, ctx):
        """Automatically sends news about new features
        """
        if ctx.invoked_subcommand is None:
            return await self.bot.send_cmd_help(ctx)

    @commands.cooldown(1, 5, BucketType.guild)
    @botnews.command(name="channel")
    async def botnews_channel(self, ctx, channel: discord.TextChannel):
        """Sets the channel to send bot news to"""
        guild = ctx.guild
        if not guild.me.permissions_in(channel).send_messages:
            return await ctx.send("I do not have permissions to send "
                                  "messages to {.mention}".format(channel))
        await self.bot.database.set_guild(
            guild, {"botnews.channel": channel.id}, self)
        doc = await self.bot.database.get_guild(guild, self)
        enabled = doc["botnews"].get("on", False)
        if enabled:
            msg = ("I will now send bot news to {.mention}.".format(channel))
        else:
            msg = ("Channel set to {.mention}. In order to receive "
                   "bot news, you still need to enable it using "
                   "`botnews toggle on`.".format(channel))
        await channel.send(msg)

    @commands.cooldown(1, 5, BucketType.guild)
    @botnews.command(name="toggle")
    async def botnews_toggle(self, ctx, on_off: bool):
        """Toggles posting bot news"""
        guild = ctx.guild
        await self.bot.database.set_guild(guild, {"botnews.on": on_off}, self)
        if on_off:
            doc = await self.bot.database.get_guild(guild, self)
            channel = doc["botnews"].get("channel")
            if channel:
                channel = guild.get_channel(channel)
                if channel:
                    msg = ("I will now send bot news to {.mention}.".format(
                        channel))
            else:
                msg = ("Bot news toggled on. In order to receive "
                       "bot news, you still need to set a channel using "
                       "`botnews channel <channel>`.".format(channel))
        else:
            msg = ("Bot news disabled")
        await ctx.send(msg)


def setup(bot):
    bot.add_cog(Meta(bot))
