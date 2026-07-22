import asyncio
import logging
import discord
from discord.ext import commands
import os
import re
import aiohttp

logger = logging.getLogger(__name__)

voice_clients = {}

async def test_token(token: str) -> tuple[bool, str]:
    """Testa se o token é válido na API do Discord."""
    headers = {'Authorization': token.strip()}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get('https://discord.com/api/v9/users/@me', headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return True, f"{data['username']}#{data.get('discriminator', '0')}"
                elif resp.status == 401:
                    return False, "Token inválido (401) - copie o token corretamente."
                else:
                    return False, f"Erro {resp.status}"
        except Exception as e:
            return False, str(e)

async def connect_user_voice(token: str, guild_id: int, channel_id: int, hours: int, user_id: int):
    token = token.strip()
    if not token or len(token.split('.')) != 3:
        raise ValueError("Token inválido. Deve ter 3 partes separadas por pontos.")

    # Testa o token
    valid, msg = await test_token(token)
    if not valid:
        raise ValueError(f"Token inválido: {msg}")

    logger.info(f"✅ Token válido para {msg}")

    os.environ['DISCORD_VOICE_DRIVER'] = 'pynacl'
    intents = discord.Intents.default()
    intents.voice_states = True
    client = commands.Bot(command_prefix='!', intents=intents, self_bot=True)

    @client.event
    async def on_ready():
        logger.info(f"✅ Self-bot conectado como {client.user}")
        guild = client.get_guild(guild_id)
        if not guild:
            await client.close()
            return
        channel = guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.VoiceChannel):
            await client.close()
            return
        if guild.voice_client:
            return
        try:
            vc = await channel.connect(timeout=30.0, reconnect=True)
            voice_clients[user_id] = vc
            logger.info(f"🎧 Conectado ao canal {channel.name} por {hours}h")
            start = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start) < hours * 3600:
                await asyncio.sleep(30)
                if not vc.is_connected():
                    try:
                        await vc.connect()
                    except:
                        pass
            if vc.is_connected():
                await vc.disconnect()
        except Exception as e:
            logger.error(f"❌ Erro na voz: {e}")
        finally:
            await client.close()
            if user_id in voice_clients:
                del voice_clients[user_id]

    try:
        await client.start(token)
    except discord.LoginFailure:
        raise ValueError("Falha no login. Token inválido ou expirado.")
    except Exception as e:
        raise ValueError(f"Erro ao iniciar: {e}")

async def disconnect_user_voice(user_id: int):
    vc = voice_clients.get(user_id)
    if vc and vc.is_connected():
        await vc.disconnect()
        del voice_clients[user_id]
        return True
    return False