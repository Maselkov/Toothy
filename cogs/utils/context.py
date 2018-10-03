import asyncio

import discord
from discord.ext import commands


class ToothyContext(commands.Context):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def default_check(self, message):
        return (message.author == self.author
                and message.channel == self.channel)

    async def send_help(self):
        cmd = self.bot.get_command("help")
        await self.invoke(cmd, command=self.command.qualified_name)

    async def get_answer(self,
                         prompt=None,
                         *,
                         timeout=120,
                         timeout_message="No response in time",
                         check=None,
                         delete_answer=False,
                         return_full=False):
        if prompt:
            await self.send(prompt)
        if not check:
            check = self.default_check
        try:
            answer = await self.bot.wait_for(
                "message", timeout=timeout, check=check)
        except asyncio.TimeoutError:
            if timeout_message:
                await self.send(timeout_message)
            return None
        if delete_answer:
            try:
                await answer.delete()
            except discord.HTTPException:
                pass
        if return_full:
            return answer
        return answer.content
