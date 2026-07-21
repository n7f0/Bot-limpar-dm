import discord
from discord.ext import commands
import os
import asyncio
import traceback
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

class NexzyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
        self.initial_extensions = ["cogs.panel"]

    async def setup_hook(self):
        for cog in self.initial_extensions:
            try:
                await self.load_extension(cog)
                logger.info(f"✅ Cog carregado: {cog}")
            except Exception as e:
                logger.error(f"❌ Erro ao carregar {cog}: {e}")

    async def on_ready(self):
        logger.info(f"✅ Bot logado como {self.user} (ID: {self.user.id})")
        try:
            synced = await self.tree.sync()
            logger.info(f"✅ {len(synced)} comando(s) sincronizado(s): {[cmd.name for cmd in synced]}")
        except Exception as e:
            logger.error(f"❌ Erro ao sincronizar comandos: {e}")
        self.loop.create_task(self.update_presence())

    async def on_disconnect(self):
        logger.warning("⚠️ Bot desconectado do Discord. Tentando reconectar...")

    async def on_resumed(self):
        logger.info("✅ Conexão com o Discord restaurada.")

    async def update_presence(self):
        while True:
            try:
                if self.is_ready():
                    activity = discord.Activity(
                        type=discord.ActivityType.playing,
                        name="Nexzy Pro | /painel",
                        details=f"🧹 {len(self.users)} usuários",
                        state="Modo Stealth"
                    )
                    await self.change_presence(activity=activity, status=discord.Status.online)
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Erro na presença: {e}")
                await asyncio.sleep(10)

async def main():
    token = os.getenv('BOT_TOKEN')
    if not token:
        logger.error("❌ BOT_TOKEN não definido.")
        return

    # Loop infinito de reconexão
    while True:
        try:
            bot = NexzyBot()
            init_db()
            async with bot:
                await bot.start(token)
        except discord.errors.LoginFailure as e:
            logger.error(f"❌ Falha no login: {e}. Verifique o token.")
            break
        except Exception as e:
            logger.error(f"❌ Erro fatal no bot: {e}")
            traceback.print_exc()
            logger.info("🔄 Reiniciando o bot em 15 segundos...")
            await asyncio.sleep(15)
        else:
            logger.info("🔄 Bot encerrado. Reiniciando em 10 segundos...")
            await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())