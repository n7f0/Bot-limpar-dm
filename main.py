import os
# FORÇA O USO DO PyNaCl COMO DRIVER DE VOZ
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
        if bot.guilds:
            guild = bot.guilds[0]
            synced = await bot.tree.sync(guild=guild)
            logging.info(f"✅ {len(synced)} comando(s) sincronizado(s) no servidor '{guild.name}'")
        else:
            logging.warning("⚠️ Bot não está em nenhum servidor. Use !sync para sincronizar.")
    except Exception as e:
        logging.error(f"❌ Erro ao sincronizar: {e}")

@bot.command(name="sync")
@commands.is_owner()
async def sync_command(ctx):
    try:
        synced = await bot.tree.sync(guild=ctx.guild)
        await ctx.send(f"✅ {len(synced)} comando(s) sincronizado(s).")
    except Exception as e:
        await ctx.send(f"❌ Erro: {e}")

async def main():
    await load_cogs()
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())