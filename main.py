import os
import asyncio
import logging
import discord
from discord.ext import commands
from cogs.database import get_user_config, init_db
import threading

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    logging.error("❌ BOT_TOKEN não definido.")
    exit(1)

# ========== INICIALIZAR BANCO ==========
init_db()

# ========== BOT NORMAL (para comandos slash) ==========
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

# ========== CLIENTE SELF-BOT (para voz) ==========
user_client = None
user_token = None
voice_tasks = {}  # user_id -> task

async def start_user_client(token: str):
    """Inicia o cliente self-bot com o token do usuário."""
    global user_client, user_token
    if user_client and user_client.is_closed():
        user_client = None
    
    if user_client is None:
        # Força o driver de voz para pynacl
        os.environ['DISCORD_VOICE_DRIVER'] = 'pynacl'
        
        intents_self = discord.Intents.default()
        intents_self.voice_states = True
        intents_self.guilds = True
        user_client = discord.Client(intents=intents_self)
        
        @user_client.event
        async def on_ready():
            logging.info(f"✅ Self-bot conectado como {user_client.user} (ID: {user_client.user.id})")
        
        # Inicia o cliente
        await user_client.start(token)
    return user_client

# ========== FUNÇÃO PARA ENTRAR EM CALL COM O SELF-BOT ==========
async def join_voice_with_selfbot(user_id: int, guild_id: int, channel_id: int, hours: int):
    """Usa o self-bot para entrar em call."""
    global user_client
    
    if not user_client or not user_client.is_ready():
        # Tenta iniciar o cliente com o token salvo
        config = get_user_config(user_id)
        if not config or not config['token']:
            return "❌ Token do usuário não configurado."
        user_token = config['token']
        try:
            await start_user_client(user_token)
        except Exception as e:
            return f"❌ Erro ao iniciar self-bot: {e}"
    
    # Espera o cliente estar pronto
    await asyncio.sleep(2)  # pequena pausa
    
    guild = user_client.get_guild(guild_id)
    if not guild:
        # Tenta buscar o servidor
        guild = await user_client.fetch_guild(guild_id)
    if not guild:
        return "❌ Servidor não encontrado."
    
    channel = guild.get_channel(channel_id)
    if not channel:
        channel = await guild.fetch_channel(channel_id)
    if not channel or not isinstance(channel, discord.VoiceChannel):
        return "❌ Canal de voz não encontrado."
    
    if guild.voice_client:
        return "⚠️ Já estou em uma call neste servidor."
    
    try:
        vc = await channel.connect(timeout=30.0, reconnect=True)
        # Mantém a conexão por X horas
        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < hours * 3600:
            await asyncio.sleep(30)
            if not vc.is_connected():
                try:
                    await vc.connect()
                except:
                    pass
        if vc.is_connected():
            await vc.disconnect()
        return f"✅ Conectado ao canal `{channel.name}` por {hours}h."
    except Exception as e:
        return f"❌ Erro: {e}"

# ========== CARREGAR COGS DO BOT ==========
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
    except Exception as e:
        logging.error(f"❌ Erro ao sincronizar: {e}")

# ========== COMANDO DE SYNC ==========
@bot.command(name="sync")
@commands.is_owner()
async def sync_command(ctx):
    try:
        synced = await bot.tree.sync(guild=ctx.guild)
        await ctx.send(f"✅ {len(synced)} comando(s) sincronizado(s).")
    except Exception as e:
        await ctx.send(f"❌ Erro: {e}")

# ========== MAIN ==========
async def main():
    await load_cogs()
    # Inicia o bot normal
    await bot.start(BOT_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())