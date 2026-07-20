import discord
from discord.ext import commands
import os
import asyncio
import logging
from utils.logger import setup_logger
from utils.db import init_db
from utils.security import load_encryption_key

# Configura logging
logger = setup_logger()

# Carrega chave de criptografia
load_encryption_key()

# Configura intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

# Carrega cogs
async def load_extensions():
    await bot.load_extension("cogs.panel")
    await bot.load_extension("cogs.voice")
    await bot.load_extension("cogs.clean")
    await bot.load_extension("cogs.backup")
    await bot.load_extension("cogs.farm")
    await bot.load_extension("cogs.profile")
    await bot.load_extension("cogs.admin")

@bot.event
async def on_ready():
    logger.info(f"✅ Bot logado como {bot.user}")
    await bot.tree.sync()
    # Inicia tarefas em background (ex: health checks, agendamentos)
    bot.loop.create_task(update_presence())
    # Inicia o scheduler para tarefas agendadas
    from utils.scheduler import start_scheduler
    bot.loop.create_task(start_scheduler(bot))

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