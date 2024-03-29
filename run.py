import asyncio
import logging
import logging.handlers
import os
from toothy.toothy import DEBUG
from toothy.toothy import Toothy


def setup_logging():
    formatter = logging.Formatter(
        '%(asctime)s:%(levelname)s:%(name)s: %(message)s')
    logger = logging.getLogger("")
    if DEBUG:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    logging.getLogger("discord").setLevel(logging.INFO)
    logging.getLogger("discord.http").setLevel(logging.WARNING)
    file_hdlr = logging.handlers.RotatingFileHandler(
        filename="logs/toothy.log",
        maxBytes=10 * 1024 * 1024,
        encoding="utf-8",
        backupCount=5)
    file_hdlr.setFormatter(formatter)
    stderr_hdlr = logging.StreamHandler()
    stderr_hdlr.setFormatter(formatter)
    if DEBUG:
        stderr_hdlr.setLevel(logging.DEBUG)
    else:
        stderr_hdlr.setLevel(logging.ERROR)
    logger.addHandler(file_hdlr)
    logger.addHandler(stderr_hdlr)


async def main():
    bot = Toothy()
    print("Logging in to Discord")
    async with bot:
        await bot.start()


if __name__ == '__main__':
    if not os.path.exists("logs"):
        os.makedirs("logs")
    setup_logging()
    asyncio.run(main())
