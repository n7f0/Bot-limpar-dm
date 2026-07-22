import os
# Força o uso do PyNaCl para voz (mesmo em self‑bot)
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

# Intents para self‑bot (podem ser mais restritos, mas mantemos os mesmos)
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True

# Self‑bot: o token é de usuário, então usamos `commands.Bot` normalmente
bot = commands.Bot(command_prefix='!', intents=intents, self_bot=True)

async def load_cogs():
    try:
        await bot.load_extension("cogs.panel")
        logging.info("✅ Cog 'panel' carregado.")
    except Exception as e:
        logging.error(f"❌ Erro ao carregar cog: {e}")

@bot.event
async def on_ready():
    logging.info(f"✅ Self‑bot logado como {bot.user} (ID: {bot.user.id})")
    # Sincronização de comandos não funciona para self‑bots (só slash em bots normais)
    # Mas o painel usa botões, então não precisa de slash.
    logging.info("⚠️ Comandos slash NÃO funcionam em self‑bots. Use o botão do painel.")

async def main():
    await load_cogs()
    await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())