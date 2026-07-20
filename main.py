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
    # 🔥 CARREGA APENAS O PAINEL – SEM OUTROS COGS
    cogs = ["cogs.panel"]
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            logger.info(f"✅ Cog carregado: {cog}")
        except Exception as e:
            logger.error(f"❌ Erro ao carregar {cog}: {e}")

@bot.event
async def on_ready():
    logger.info(f"✅ Bot logado como {bot.user}")
    
    # 🔥 LIMPA TODOS OS COMANDOS ANTIGOS (remove /clean, /call, etc.)
    try:
        await bot.tree.clear_commands()
        logger.info("✅ Comandos antigos removidos globalmente.")
    except Exception as e:
        logger.error(f"❌ Erro ao limpar comandos antigos: {e}")
    
    # Sincroniza apenas o comando atual (/paineldm)
    try:
        synced = await bot.tree.sync()
        logger.info(f"✅ {len(synced)} comando(s) sincronizado(s): {[cmd.name for cmd in synced]}")
    except Exception as e:
        logger.error(f"❌ Erro ao sincronizar comandos: {e}")
    
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
            logger.error(f"Erro na presença: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    async def main():
        async with bot:
            init_db()
            await load_extensions()
            token = os.getenv('BOT_TOKEN')
            if not token:
                logger.error("❌ BOT_TOKEN não definido.")
                return
            await bot.start(token)
    asyncio.run(main())