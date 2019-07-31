import json
import logging

from discord.ext import commands

log = logging.getLogger(__name__)


class BotSite:
    def __init__(self, bot, data):
        self.bot = bot
        self.token = data["token"]
        self.url = data["url"].format(bot.user.id)
        self.template = data["template"]

    async def post(self):
        if not self.token:
            return
        payload_template = {
            "guild_count": len(self.bot.guilds),
            "shard_count": len(self.bot.shards)
        }
        payload = {}
        for key, value in payload_template.items():
            if key in self.template:
                payload[self.template[key]] = value
        headers = {
            "Authorization": self.token,
            "Content-Type": "application/json"
        }
        async with self.bot.session.post(
                self.url, data=json.dumps(payload), headers=headers) as r:
            log.info("Url: {} Payload: {} Response: {}".format(
                self.url, payload, r.status))


class ListingSites(commands.Cog):
    """Posting your bot information to bot listing sites"""

    def __init__(self, bot):
        self.bot = bot
        self.sites = []
        self.load_sites()

    async def cog_check(self, ctx):
        return await self.bot.is_owner(ctx.author)

    @commands.command()
    async def reloadsites(self, ctx):
        """Reload bot listing site information"""
        self.load_sites()
        await ctx.send("Listing sites reloaded")

    def load_sites(self):
        with open("settings/botsites.json", encoding="utf-8", mode="r") as f:
            self.sites = [BotSite(self.bot, data) for data in json.load(f)]

    async def post_stats(self):
        for site in self.sites:
            await site.post()

    @commands.Cog.listener()
    async def on_ready(self):
        await self.post_stats()

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        await self.post_stats()

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        await self.post_stats()


def setup(bot):
    cog = ListingSites(bot)
    bot.add_cog(cog)
