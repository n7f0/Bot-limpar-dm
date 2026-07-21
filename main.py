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
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

async def load_extensions():
    try:
        await bot.load_extension("cogs.panel")
        logger.info("✅ Cog carregado: cogs.panel")
    except Exception as e:
        logger.error(f"❌ Erro ao carregar cogs.panel: {e}")

@bot.event
async def on_ready():
    logger.info(f"✅ Bot logado como {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        logger.info(f"✅ {len(synced)} comando(s) sincronizado(s): {[cmd.name for cmd in synced]}")
    except Exception as e:
        logger.error(f"❌ Erro ao sincronizar comandos: {e}")

@bot.event
async def on_disconnect():
    logger.warning("⚠️ Bot desconectado do Discord.")

@bot.event
async def on_resumed():
    logger.info("✅ Conexão restaurada.")

if __name__ == "__main__":
    token = os.getenv('BOT_TOKEN')
    if not token:
        logger.error("❌ BOT_TOKEN não definido.")
        exit(1)

    while True:
        try:
            asyncio.run(bot.start(token))
        except discord.errors.LoginFailure as e:
            logger.error(f"❌ Falha no login: {e}. Verifique o token.")
            break
        except Exception as e:
            logger.error(f"❌ Erro: {e}. Reiniciando em 10s...")
            import traceback
            traceback.print_exc()
            asyncio.sleep(10)