import discord
from discord.ext import commands
import os
import asyncio
from utils.logger import get_logger
from utils.db import init_db
from utils.security import load_encryption_key

logger = get_logger()

load_encryption_key()

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

async def load_extensions():
    # Lista de todos os cogs
    cogs = [
        "cogs.panel",
        "cogs.voice",
        "cogs.clean",
        "cogs.backup",
        "cogs.farm",
        "cogs.profile",
        "cogs.admin"
    ]
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            logger.info(f"✅ Cog carregado: {cog}")
        except Exception as e:
            logger.error(f"❌ Erro ao carregar {cog}: {e}")

@bot.event
async def on_ready():
    logger.info(f"✅ Bot logado como {bot.user}")
    await bot.tree.sync()
    bot.loop.create_task(update_presence())

async def update_presence():
    while True:
        try:
            if bot.is_ready():
                activity = discord.Activity(
                    type=discord.ActivityType.playing,
                    name="Nexzy Pro",
                    details=f"🧹 {len(bot.users)} usuários",
                    state="Modo Stealth"
                )
                await bot.change_presence(activity=activity, status=discord.Status.online)
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Erro ao atualizar presença: {e}")

if __name__ == "__main__":
    async def main():
        async with bot:
            await load_extensions()
            await bot.start(os.getenv('BOT_TOKEN'))
    asyncio.run(main())