import collections
import datetime
from collections import Counter

import discord
from discord import app_commands
from discord.ext import commands

STATS_PIPELINE = [{
    "$facet": {
        "getTop10Commands": [{
            "$group": {
                "_id": "$command",
                "count": {
                    "$sum": 1
                }
            }
        }, {
            "$sort": {
                "count": -1
            }
        }, {
            "$limit": 10
        }],
        "totalCommandCount": [{
            "$group": {
                "_id": None,
                "count": {
                    "$sum": 1
                }
            }
        }]
    }
}]


class Statistics(commands.GroupCog, name="statistics"):
    """Bot statistics"""

    def __init__(self, bot):
        self.bot = bot
        self.counter = Counter()
        self.db = self.bot.database.db.statistics

    @app_commands.checks.cooldown(1, 10, key=lambda i: i.user.id)
    @app_commands.command(name="user")
    @app_commands.describe(reveal="Post the response as a publicly "
                           "visible message. Defaults to False")
    async def statistics_user(self,
                              interaction: discord.Interaction,
                              reveal: bool = False):
        """Statistics of the user"""
        await interaction.response.defer(ephemeral=not reveal)
        data = discord.Embed(description="Command usage "
                             f"statistics of {interaction.user.mention}",
                             color=self.bot.color)
        match = [{"$match": {"author": interaction.user.id}}]
        facets = await self.db.commands.aggregate(match +
                                                  STATS_PIPELINE).to_list(None)
        facets = facets[0]
        data = await self.generate_embed(interaction, data, facets, rank=False)
        await interaction.followup.send(embed=data)

    @app_commands.command(name="server")
    @app_commands.checks.cooldown(1, 60, key=lambda i: i.guild_id)
    @app_commands.guild_only()
    async def statistics_guild(self, interaction: discord.Interaction):
        """Statistics of this server"""
        await interaction.response.defer()
        data = discord.Embed(description="Command usage "
                             f"statistics of {interaction.guild.name}",
                             color=self.bot.color)
        match = [{"$match": {"guild": interaction.guild.id}}]
        facets = await self.db.commands.aggregate(match +
                                                  STATS_PIPELINE).to_list(None)
        facets = facets[0]
        data = await self.generate_embed(interaction, data, facets, rank=False)
        await interaction.followup.send(embed=data)

    @app_commands.checks.cooldown(1, 3600, key=lambda i: i.user.id)
    @app_commands.command(name="global")
    async def statistics_total(self, interaction: discord.Interaction):
        """Total stats of the bot's commands

        Only available to server owner"""
        await interaction.response.defer()
        data = discord.Embed(description="Global command usage statistics.",
                             color=self.bot.color)
        facets = await self.db.commands.aggregate(STATS_PIPELINE).to_list(None)
        facets = facets[0]
        data = await self.generate_embed(interaction, data, facets, rank=False)
        await interaction.followup.send(embed=data)

    async def get_commands_stats(self, cursor, search):
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
        for doc in ordered_commands:
            percentages[doc["_id"]] = round(100 / total * doc["count"])
        ordered_percentages = collections.OrderedDict(
            sorted(percentages.items(), key=lambda x: x[1], reverse=True))
        return ordered_percentages

    async def generate_embed(self, ctx, embed, facets, *, rank=True):
        # Get data
        total_amount = facets["totalCommandCount"][0]["count"]
        ordered_commands = facets["getTop10Commands"]
        percentages = self.calc_percentage(ordered_commands, total_amount)
        embed.add_field(name="Total commands used",
                        value=str(total_amount),
                        inline=False)
        output = self.generate_commands(ordered_commands)
        embed.add_field(name="Most used commands", value=output, inline=False)
        output = self.generate_diagram(percentages)
        embed.add_field(name="Diagram", value=output, inline=False)

        return embed

    def generate_commands(self, ordered_commands):
        """Returns the 10 most used commands from ordered_commands"""
        seq = [k["_id"] for k in ordered_commands]
        longest = len(max(seq, key=len))
        if longest < 7:
            longest = 7
        output = [
            "COMMAND{}COUNT".format(" " * (longest - 4)),
            "--------{}|-----".format("-" * (longest - 6))
        ]
        counter = 0
        for doc in ordered_commands:
            if counter > 9:
                break
            output.append("{} {} | {}".format(
                doc["_id"].upper(), " " * (longest - len(doc["_id"])),
                doc["count"]))
            counter += 1
        output.append("--------{}------".format(
            "-" * (longest - len("command") + 2)))
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
                user = await self.bot.fetch_user(k)
                if user is None:
                    user = "Unknown"
                output += "{}. | {} | used {} commands\n".format(
                    counter, user, v)
        return output

    def get_bot_uptime(self, *, brief=False):
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

    @commands.Cog.listener()
    async def on_message(self, message):
        self.counter["messages"] += 1

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if not interaction.command:
            return
        self.counter["invoked_commands"] += 1
        guild = interaction.guild.id if interaction.guild else None
        channel = interaction.channel.id if interaction.channel else None
        doc = {
            "author": interaction.user.id,
            "guild": guild,
            "channel": channel,
            "command": interaction.command.qualified_name,
            "timestamp": interaction.created_at
        }
        await self.db.commands.insert_one(doc)


async def setup(bot):
    await bot.add_cog(Statistics(bot))
