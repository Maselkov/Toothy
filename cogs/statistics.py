import datetime
from collections import Counter
import collections

import discord
from discord.ext import commands


class Statistics:
    """Bot statistics"""

    def __init__(self, bot):
        self.bot = bot
        self.counter = Counter()
        self.db = self.bot.database.db.statistics

    @commands.group()
    async def statistics(self, ctx):
        """Statistic related commands"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)

    @statistics.command(name="user")
    async def statistics_user(self, ctx):
        """Statistics of the user"""
        counter = 0
        output = ""
        cursor = self.db.commands.find({"author": ctx.author.id})
        total_amount = await cursor.count()

        data = discord.Embed(
            description="Command statistics of {0}".format(ctx.author))
        data.add_field(
            name="Total commands", value=str(total_amount), inline=False)

        ordered_commands = await self.get_commands(cursor)
        for k, v in ordered_commands.items():
            output += "{0} used {1} times\n".format(k.capitalize(), v)
        data.add_field(name="Most used commands", value=output, inline=False)

        try:
            await ctx.send(embed=data)
        except discord.Forbidden:
            await ctx.send("Need permission to embed links")

    @statistics.command(name="guild")
    async def statistics_guild(self, ctx):
        """Statistics of this guild

        Only available on Discord Server"""
        if ctx.guild is None:
            return await self.bot.send_cmd_help(ctx)
        output = ""
        counter = 0
        cursor = self.db.commands.find({"guild": ctx.guild.id})
        total_amount = await cursor.count()

        data = discord.Embed(
            description="Command statistics of {0}".format(ctx.guild))
        data.add_field(
            name="Total commands", value=str(total_amount), inline=False)

        ordered_commands = await self.get_commands(cursor)
        percentages = self.calc_percentage(ordered_commands, total_amount)
        ranking = await self.collect_users(cursor)
        for k, v in ordered_commands.items():
            if counter < 11:
                output += "{0} used {1} times\n".format(k.capitalize(), v)
                counter += 1
        counter = 0
        output += "\n"
        for k, v in percentages.items():
            if counter < 5:
                #output += "{0}% used the command {1}".format(v, k)
                for emoji in range(0,round(v/10)):
                    output += ":eggplant:"
                output += " {0}% used {1}\n".format(v,k)
                counter +=1
        data.add_field(name="Most used commands", value=output, inline=False)
        counter = 0
        output = ""
        for k,v in ranking:
            if counter < 5:
                output += "{0}. {1} has sent {2} commands.\n".format(counter, k, v)
        data.add_field(name="Ranking", value="asdf" + output, inline=False)

        try:
            await ctx.send(embed=data)
        except discord.Forbidden:
            await ctx.send("Need permission to embed links")

    async def get_commands(self, cursor):
        """Collect commands, returns formatted output string"""
        commands = {}
        async for stat in cursor:
            if stat['command'] in commands:
                commands[stat['command']] += 1
            else:
                commands[stat['command']] = 1
        ordered_commands = collections.OrderedDict(
            sorted(commands.items(), key=lambda x: x[1], reverse=True))
        return ordered_commands

    def calc_percentage(self, ordered_commands, total):
        percentages = {}
        for k, v in ordered_commands.items():
            percentages[k] = round(100 / total * v)
        ordered_percentages = collections.OrderedDict(
            sorted(percentages.items(), key=lambda x: x[1], reverse=True))
        return ordered_percentages

    async def collect_users(self, cursor):
        users = {}
        async for stat in cursor:
            if stat['author'] in users:
                users[stat['author']] += 1
            else:
                users[stat['author']] = 1
        ordered_commands = collections.OrderedDict(
            sorted(users.items(), key=lambda x: x[1], reverse=True))
        return ordered_commands

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
