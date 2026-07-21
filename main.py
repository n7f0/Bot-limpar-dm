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
    cogs = ["cogs.panel"]
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            logger.info(f"✅ Cog carregado: {cog}")
        except Exception as e:
            logger.error(f"❌ Erro ao carregar {cog}: {e}")

@bot.event
async def on_ready():
    logger.info(f"✅ Bot logado como {bot.user} (ID: {bot.user.id})")
    # Sincroniza comandos sem limpar (evita erro)
    try:
        synced = await bot.tree.sync()
        logger.info(f"✅ {len(synced)} comando(s) sincronizado(s): {[cmd.name for cmd in synced]}")
    except Exception as e:
        logger.error(f"❌ Erro ao sincronizar comandos: {e}")
    bot.loop.create_task(update_presence())

@bot.event
async def on_disconnect():
    logger.warning("⚠️ Bot desconectado do Discord. Tentando reconectar...")
    # O bot já tenta reconectar automaticamente, mas podemos logar

@bot.event
async def on_resumed():
    logger.info("✅ Conexão com o Discord restaurada.")

async def update_presence():
    while True:
        try:
            if bot.is_ready():
                activity = discord.Activity(
                    type=discord.ActivityType.playing,
                    name="Nexzy Pro | /painel",
                    details=f"🧹 {len(bot.users)} usuários",
                    state="Modo Stealth"
                )
                await bot.change_presence(activity=activity, status=discord.Status.online)
            await asyncio.sleep(60)
        except Exception as e:
            logger.error(f"Erro na presença: {e}")
            await asyncio.sleep(10)

async def run_bot():
    token = os.getenv('BOT_TOKEN')
    if not token:
        logger.error("❌ BOT_TOKEN não definido.")
        return
    # Loop de reconexão manual (redundante, mas seguro)
    while True:
        try:
            async with bot:
                init_db()
                await load_extensions()
                await bot.start(token)
        except discord.errors.ConnectionClosed as e:
            logger.error(f"❌ Conexão fechada: {e}. Reconectando em 10s...")
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"❌ Erro fatal: {e}. Reiniciando em 10s...")
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(run_bot())