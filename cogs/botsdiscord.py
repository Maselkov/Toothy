import json
import logging

import aiohttp
from discord.ext import commands

log = logging.getLogger(__name__)


class BotsDiscord:
    """Posting your bot information to bot listing sites"""

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession(loop=self.bot.loop)

    def __unload(self):
        self.session.close()

    async def __local_check(self, ctx):
        return await self.bot.is_owner(ctx.author)

    @commands.command()
    async def botspwtoken(self, ctx, token: str):
        """Token for bots.discord.pw"""
        await self.bot.database.set_cog_config(self, {"dbotspw_token": token})
        await ctx.send("Token set")

    @commands.command()
    async def botsorgtoken(self, ctx, token: str):
        """Token for discordbots.org"""
        await self.bot.database.set_cog_config(self, {"dbotsorg_token": token})
        await ctx.send("Token set")

    async def post_payload(self, base_url, token):
        url = base_url + "api/bots/{}/stats".format(self.bot.user.id)
        payload = {"server_count": len(self.bot.guilds)}
        headers = {"Authorization": token, "Content-Type": "application/json"}
        async with self.session.post(
                url, data=json.dumps(payload), headers=headers) as r:
            log.info("Payload: {} Response: {}".format(payload, r.status))

    async def post_dbotspw(self, doc):
        if not doc:
            return
        token = doc.get("dbotspw_token")
        if not token:
            return
        url = "https://bots.discord.pw/"
        await self.post_payload(url, token)

    async def post_dbotsorg(self, doc):
        if not doc:
            return
        token = doc.get("dbotsorg_token")
        if not token:
            return
        url = "https://discordbots.org/"
        await self.post_payload(url, token)

    async def post_stats(self):
        doc = await self.bot.database.get_cog_config(self)
        await self.post_dbotspw(doc)
        await self.post_dbotsorg(doc)

    async def on_ready(self):
        await self.post_stats()

    async def on_guild_remove(self, guild):
        await self.post_stats()

    async def on_guild_join(self, guild):
        await self.post_stats()


def setup(bot):
    cog = BotsDiscord(bot)
    bot.loop.create_task(
        bot.database.setup_cog(cog, {
            "dbotsorg_token": None,
            "dbotspw_token": None
        }))
    bot.add_cog(cog)
