import json
import logging

import aiohttp
from discord.ext import commands

log = logging.getLogger(__name__)


class BotsDiscord:
    """Posting your bot information to bots discord pw"""

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession(loop=self.bot.loop)

    def __unload(self):
        self.session.close()

    async def __local_check(self, ctx):
        return await self.bot.is_owner(ctx.author)

    @commands.command()
    async def botstoken(self, ctx, token: str):
        """Token for bots.discord.pw"""
        await self.bot.database.set_cog_config(self, {"token": token})
        await ctx.send("Token set")

    async def post_stats(self):
        doc = await self.bot.database.get_cog_config(self)
        if not doc:
            return
        token = doc["token"]
        if token is None:
            return
        url = "https://bots.discord.pw/api/bots/{}/stats".format(
            self.bot.user.id)
        headers = {"Authorization": token, "Content-Type": "application/json"}
        payload = {"server_count": len(self.bot.guilds)}
        async with self.session.post(
            url, data=json.dumps(payload), headers=headers) as r:
            log.info("Payload: {} Response: {}".format(payload, r.status))

    async def on_ready(self):
        await self.post_stats()

    async def on_guild_remove(self, guild):
        await self.post_stats()

    async def on_guild_join(self, guild):
        await self.post_stats()


def setup(bot):
    cog = BotsDiscord(bot)
    bot.loop.create_task(bot.database.setup_cog(cog, {"token": None}))
    bot.add_cog(cog)
