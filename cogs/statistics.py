import collections
import datetime
from collections import Counter

import discord
from discord.ext import commands
from discord.ext.commands.cooldowns import BucketType


class Statistics:
    """Bot statistics"""

    def __init__(self, bot):
        self.bot = bot
        self.counter = Counter()
        self.db = self.bot.database.db.statistics

    @commands.group(aliases=["stats"])
    async def statistics(self, ctx):
        """Statistic related commands"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)

    @statistics.command(name="user")
    @commands.cooldown(1, 15, BucketType.user)
    async def statistics_user(self, ctx):
        """Statistics of the user"""
        async with ctx.typing():
            cursor = self.db.commands.find({"author": ctx.author.id})
            data = discord.Embed(
                description="Command usage statistics of {0}".format(
                    ctx.author),
                color=self.bot.color)
            data = await self.generate_embed(ctx, data, cursor, rank=False)
            try:
                await ctx.send(embed=data)
            except discord.Forbidden:
                await ctx.send("Need permission to embed links")

    @statistics.command(name="server")
    @commands.guild_only()
    @commands.cooldown(1, 15, BucketType.guild)
    async def statistics_server(self, ctx):
        """Statistics of this serverr"""
        async with ctx.typing():
            cursor = self.db.commands.find({"guild": ctx.guild.id})
            data = discord.Embed(
                description="Command usage statistics of {0}".format(
                    ctx.guild),
                color=self.bot.color)
            data = await self.generate_embed(ctx, data, cursor)
            try:
                await ctx.send(embed=data)
            except discord.Forbidden:
                await ctx.send("Need permission to embed links")

    @statistics.command(name="total")
    @commands.is_owner()
    async def statistics_total(self, ctx):
        """Total stats of the bot's commands

        Only available to server owner"""
        async with ctx.typing():
            cursor = self.db.commands.find()
            data = discord.Embed(
                description="Total command statistics", color=self.bot.color)
            data = await self.generate_embed(ctx, data, cursor)
            try:
                await ctx.send(embed=data)
            except discord.Forbidden:
                await ctx.send("Need permission to embed links")

    async def get_commands(self, cursor, search):
        """Returns ordered dict of commands from cursor
        and search string in DB"""
        commands = {}
        async for stat in cursor:
            if stat[search] in commands:
                commands[stat[search]] += 1
            else:
                commands[stat[search]] = 1
        ordered_commands = collections.OrderedDict(
            sorted(commands.items(), key=lambda x: x[1], reverse=True))
        return ordered_commands

    def calc_percentage(self, ordered_commands, total):
        """Generates ordered dict of percentages of
        used commands from ordered_commands"""
        percentages = {}
        for k, v in ordered_commands.items():
            percentages[k] = round(100 / total * v)
        ordered_percentages = collections.OrderedDict(
            sorted(percentages.items(), key=lambda x: x[1], reverse=True))
        return ordered_percentages

    async def generate_embed(self, ctx, data, cursor, *, rank=True):
        # Get data
        total_amount = await cursor.count()
        ordered_commands = await self.get_commands(cursor, 'command')
        percentages = self.calc_percentage(ordered_commands, total_amount)
        data.add_field(
            name="Total commands used", value=str(total_amount), inline=False)
        output = self.generate_commands(ordered_commands)
        data.add_field(name="Most used commands", value=output, inline=False)
        output = self.generate_diagram(percentages)
        data.add_field(name="Diagram", value=output, inline=False)
        if rank:
            cursor = cursor.rewind()
            ranking = await self.get_commands(cursor, 'author')
            output = await self.generate_ranking(ctx, ranking)
            data.add_field(
                name="Ranking", value="```{0}```".format(output), inline=False)
        return data

    def generate_commands(self, ordered_commands):
        """Returns the 10 most used commands from ordered_commands"""
        seq = [k for k, v in ordered_commands.items() if v]
        longest = len(max(seq, key=len))
        if longest < 7:
            longest = 7
        output = [
            "COMMAND{}COUNT".format(" " * (longest - 4)),
            "--------{}|-----".format("-" * (longest - 6))
        ]
        counter = 0
        for k, v in ordered_commands.items():
            if counter > 9:
                break
            if v:
                output.append("{} {} | {}".format(k.upper(), " " * (
                    longest - len(k)), v))
                counter += 1
        output.append(
            "--------{}------".format("-" * (longest - len("command") + 2)))
        output = "```ml\n{}```".format("\n".join(output))
        return output

    def generate_diagram(self, percentages):
        """Generates string of ASCII bar out of ordered_dict of percentages"""
        counter = 0
        output = "```\n"
        for k, v in percentages.items():
            if counter < 5:
                bar_count = round(v / 5)
                for emoji in range(bar_count):
                    output += "▓"
                tab_count = 20 - bar_count
                for tab in range(tab_count):
                    output += "░"
                output += " {0}% used {1}\n".format(v, k)
                counter += 1
        return output + "```"

    async def generate_ranking(self, ctx, ranking):
        """Returns the first 5 users that used the most commands"""
        counter = 0
        output = ""
        for k, v in ranking.items():
            if counter < 5:
                counter += 1
                user = await self.bot.get_user_info(k)
                if user is None:
                    user = "Unknown"
                output += "{}. | {} | used {} commands\n".format(
                    counter, user, v)
        return output

    @commands.command()
    async def uptime(self, ctx):
        """Display bot's uptime"""
        await ctx.send("Up for: `{}`".format(self.get_bot_uptime()))

    def get_bot_uptime(self, *, brief=False):
        # https://github.com/Rapptz/RoboDanny/blob/c8fef9f07145cef6c05416dc2421bbe1d05e3d33/cogs/stats.py#L108
        now = datetime.datetime.utcnow()
        delta = now - self.bot.uptime
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        days, hours = divmod(hours, 24)

        if not brief:
            if days:
                fmt = '{d} days, {h} hours, {m} minutes, and {s} seconds'
            else:
                fmt = '{h} hours, {m} minutes, and {s} seconds'
        else:
            fmt = '{h}h {m}m {s}s'
            if days:
                fmt = '{d}d ' + fmt

        return fmt.format(d=days, h=hours, m=minutes, s=seconds)

    async def on_message(self, message):
        self.counter["messages"] += 1

    async def on_command(self, ctx):
        self.counter["invoked_commands"] += 1
        guild = ctx.guild.id if ctx.guild else None
        channel = ctx.channel.id if ctx.channel else None
        doc = {
            "author": ctx.author.id,
            "guild": guild,
            "channel": channel,
            "message": ctx.message.id,
            "command": ctx.command.qualified_name,
            "timestamp": ctx.message.created_at
        }
        await self.db.commands.insert_one(doc)


def setup(bot):
    bot.add_cog(Statistics(bot))
