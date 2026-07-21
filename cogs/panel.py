import discord
from discord.ext import commands
import os
import asyncio
import logging

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

async def load_extensions():
    try:
        await bot.load_extension("cogs.panel")
        logging.info("✅ Cog carregado: cogs.panel")
    except Exception as e:
        # Mostra o erro exato e completo no console do Portainer
        logging.error(f"❌ Erro crítico ao carregar cogs.panel: {type(e).__name__} - {e}")
        import traceback
        traceback.print_exc()

# Hook para carregar as extensões antes de ligar o bot
async def setup_hook():
    await load_extensions()

bot.setup_hook = setup_hook

@bot.event
async def on_ready():
    logging.info(f"✅ Bot logado como {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        logging.info(f"✅ {len(synced)} comando(s) sincronizado(s): {[cmd.name for cmd in synced]}")
    except Exception as e:
        logging.error(f"❌ Erro ao sincronizar: {e}")

@bot.event
async def on_disconnect():
    logging.warning("⚠️ Bot desconectado. Reconectando automaticamente...")

@bot.event
async def on_resumed():
    logging.info("✅ Conexão restaurada.")

if __name__ == "__main__":
    token = os.getenv('BOT_TOKEN')
    if not token:
        logging.error("❌ BOT_TOKEN não definido.")
        exit(1)

    while True:
        try:
            asyncio.run(bot.start(token))
        except discord.errors.LoginFailure as e:
            logging.error(f"❌ Falha no login: {e}. Verifique o token.")
            break
        except Exception as e:
            logging.error(f"❌ Erro fatal: {e}. Reiniciando em 10s...")
            import traceback
            traceback.print_exc()
            asyncio.sleep(10)
