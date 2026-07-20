import discord
from discord.ext import commands
import os
import asyncio
from utils.logger import get_logger
from utils.db import init_db
from utils.security import load_encryption_key

# Inicializa logger
logger = get_logger()

# Carrega chave de criptografia (para tokens)
load_encryption_key()

# Configura intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

# Cria o bot
bot = commands.Bot(command_prefix='!', intents=intents)

# ============================================================
# CARREGAMENTO DE COGS (RESILIENTE)
# ============================================================
async def load_extensions():
    """Carrega todos os cogs, continuando mesmo se algum falhar."""
    cogs = [
        "cogs.panel",
        "cogs.voice",
        "cogs.clean",
        "cogs.backup",
        "cogs.farm",
        "cogs.profile",
        "cogs.admin"
    ]
    
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            logger.info(f"✅ Cog carregado: {cog}")
        except Exception as e:
            logger.error(f"❌ Erro ao carregar {cog}: {e}")

# ============================================================
# EVENTO ON_READY
# ============================================================
@bot.event
async def on_ready():
    logger.info(f"✅ Bot logado como {bot.user} (ID: {bot.user.id})")
    
    # Sincroniza os comandos slash
    try:
        synced = await bot.tree.sync()
        logger.info(f"✅ {len(synced)} comandos slash sincronizados.")
    except Exception as e:
        logger.error(f"❌ Erro ao sincronizar comandos: {e}")
    
    # Inicia tarefa de presença
    bot.loop.create_task(update_presence())
    
    # Inicia o scheduler (se implementado)
    try:
        from utils.scheduler import start_scheduler
        bot.loop.create_task(start_scheduler(bot))
    except ImportError:
        logger.warning("Scheduler não encontrado – ignorando.")

# ============================================================
# PRESENÇA (RICH PRESENCE)
# ============================================================
async def update_presence():
    """Atualiza a presença do bot a cada 30 segundos."""
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
            await asyncio.sleep(10)

# ============================================================
# PONTO DE ENTRADA
# ============================================================
if __name__ == "__main__":
    async def main():
        async with bot:
            # Inicializa banco de dados
            init_db()
            # Carrega cogs
            await load_extensions()
            # Inicia o bot
            token = os.getenv('BOT_TOKEN')
            if not token:
                logger.error("❌ BOT_TOKEN não definido nas variáveis de ambiente.")
                return
            await bot.start(token)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot encerrado pelo usuário.")
    except Exception as e:
        logger.error(f"Erro fatal: {e}", exc_info=True)