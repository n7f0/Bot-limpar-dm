import os
import asyncio
import logging
from discord.ext import commands

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN:
    logging.error("❌ BOT_TOKEN não definido.")
    exit(1)

intents = discord.Intents.default()
intents.message_content = True   # necessário para ler comandos com prefixo (caso use)
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

async def load_cogs():
    try:
        await bot.load_extension("cogs.panel")
        logging.info("✅ Cog 'panel' carregado com sucesso.")
    except Exception as e:
        logging.error(f"❌ Erro ao carregar cog: {e}")

@bot.event
async def on_ready():
    logging.info(f"✅ Bot logado como {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        logging.info(f"✅ {len(synced)} comando(s) slash sincronizado(s): {[cmd.name for cmd in synced]}")
    except Exception as e:
        logging.error(f"❌ Erro ao sincronizar comandos: {e}")

async def main():
    await load_cogs()
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())