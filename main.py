import os
# FORÇA O USO DO PyNaCl COMO DRIVER DE VOZ - DEVE SER A PRIMEIRA COISA
os.environ['DISCORD_VOICE_DRIVER'] = 'pynacl'

import asyncio
import logging
import discord
from discord.ext import commands

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN:
    logging.error("❌ BOT_TOKEN não definido.")
    exit(1)

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

async def load_cogs():
    try:
        await bot.load_extension("cogs.panel")
        logging.info("✅ Cog 'panel' carregado.")
    except Exception as e:
        logging.error(f"❌ Erro ao carregar cog: {e}")

@bot.event
async def on_ready():
    logging.info(f"✅ Bot logado como {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        logging.info(f"✅ {len(synced)} comando(s) sincronizado(s): {[cmd.name for cmd in synced]}")
    except Exception as e:
        logging.error(f"❌ Erro ao sincronizar: {e}")

async def main():
    await load_cogs()
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())