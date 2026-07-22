import asyncio
import logging
import discord
from discord.ext import commands
import os

logger = logging.getLogger(__name__)

# Armazena os clients de voz ativos por usuário
voice_clients = {}  # user_id -> discord.VoiceClient

async def connect_user_voice(token: str, guild_id: int, channel_id: int, hours: int, user_id: int):
    """
    Conecta a conta do usuário (self-bot) em um canal de voz.
    Mantém a conexão por X horas.
    """
    # Força o driver de voz para pynacl
    os.environ['DISCORD_VOICE_DRIVER'] = 'pynacl'
    
    # Cria um client para o usuário (self-bot)
    intents = discord.Intents.default()
    intents.voice_states = True
    client = commands.Bot(command_prefix='!', intents=intents, self_bot=True)
    
    @client.event
    async def on_ready():
        logger.info(f"✅ Self-bot conectado como {client.user} (ID: {client.user.id})")
        
        # Busca o servidor e canal
        guild = client.get_guild(guild_id)
        if not guild:
            logger.error(f"❌ Servidor {guild_id} não encontrado")
            await client.close()
            return
            
        channel = guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.VoiceChannel):
            logger.error(f"❌ Canal de voz {channel_id} não encontrado")
            await client.close()
            return
            
        # Verifica se já está conectado
        if guild.voice_client:
            logger.info("⚠️ Já estou em uma call neste servidor")
            return
            
        try:
            vc = await channel.connect(timeout=30.0, reconnect=True)
            voice_clients[user_id] = vc
            logger.info(f"🎧 Conectado ao canal {channel.name} por {hours}h")
            
            # Mantém a conexão por X horas
            start_time = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start_time) < hours * 3600:
                await asyncio.sleep(30)
                if not vc.is_connected():
                    logger.info("🔄 Reconectando...")
                    try:
                        await vc.connect()
                    except:
                        pass
                        
            if vc.is_connected():
                await vc.disconnect()
                logger.info(f"🔇 Desconectado após {hours}h")
                
        except Exception as e:
            logger.error(f"❌ Erro na voz: {e}")
        finally:
            await client.close()
            if user_id in voice_clients:
                del voice_clients[user_id]
    
    try:
        await client.start(token)
    except Exception as e:
        logger.error(f"❌ Erro ao iniciar self-bot: {e}")
        raise

async def disconnect_user_voice(user_id: int):
    """Desconecta a voz do usuário."""
    vc = voice_clients.get(user_id)
    if vc and vc.is_connected():
        await vc.disconnect()
        del voice_clients[user_id]
        return True
    return False