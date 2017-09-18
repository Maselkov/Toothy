import time

import discord
from discord.ext import commands


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


def setup(bot):
    bot.add_cog(Meta(bot))
