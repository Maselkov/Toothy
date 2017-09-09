import datetime
from collections import Counter

from discord.ext import commands


class Statistics:
    """Bot statistics"""

    def __init__(self, bot):
        self.bot = bot
        self.counter = Counter()
        self.db = self.bot.database.db.statistics

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
