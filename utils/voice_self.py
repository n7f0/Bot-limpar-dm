import asyncio
import aiohttp
import logging
import json

logger = logging.getLogger(__name__)

voice_tasks = {}

async def get_user_info(token: str):
    """Obtém informações do usuário para validar o token."""
    headers = {'Authorization': token}
    async with aiohttp.ClientSession() as session:
        async with session.get('https://discord.com/api/v9/users/@me', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            return None

async def get_user_guilds(token: str):
    """Lista os servidores do usuário para validar se ele está no servidor."""
    headers = {'Authorization': token}
    async with aiohttp.ClientSession() as session:
        async with session.get('https://discord.com/api/v9/users/@me/guilds', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            return []

async def join_voice_call(token: str, guild_id: int, channel_id: int, hours: int, user_id: int):
    """
    Entra em um canal de voz usando token de usuário (self-bot) via REST.
    Mantém a conexão por X horas com keepalive.
    """
    headers = {
        'Authorization': token,
        'Content-Type': 'application/json'
    }

    # 1. Valida o token e obtém informações do usuário
    user = await get_user_info(token)
    if not user:
        logger.error("❌ Token inválido ou expirado. Obtenha um novo token.")
        return

    logger.info(f"✅ Token válido para {user['username']}#{user.get('discriminator', '0')} (ID: {user['id']})")

    # 2. Verifica se o usuário está no servidor
    guilds = await get_user_guilds(token)
    guild_ids = [g['id'] for g in guilds]
    if str(guild_id) not in guild_ids:
        logger.error(f"❌ Você não está no servidor {guild_id}. Verifique o ID.")
        return

    logger.info(f"✅ Você está no servidor {guild_id}")

    # 3. Verifica se o canal de voz existe (tenta obter informações do canal)
    # Não há uma rota direta para obter um canal específico sem permissões de bot,
    # mas podemos tentar entrar na call e capturar o erro.
    async with aiohttp.ClientSession() as session:
        # 4. Tenta entrar no canal de voz
        url = f'https://discord.com/api/v9/guilds/{guild_id}/voice-states/@me'
        payload = {'channel_id': str(channel_id)}
        
        try:
            async with session.patch(url, headers=headers, json=payload) as resp:
                if resp.status == 204:
                    logger.info(f"✅ Entrou no canal de voz (ID: {channel_id})")
                else:
                    error_text = await resp.text()
                    logger.error(f"❌ Falha ao entrar na call: {resp.status} - {error_text}")
                    return
        except Exception as e:
            logger.error(f"❌ Erro ao entrar na call: {e}")
            return

        # 5. Mantém a conexão ativa por X horas
        start_time = asyncio.get_event_loop().time()
        end_time = start_time + (hours * 3600)

        while asyncio.get_event_loop().time() < end_time:
            await asyncio.sleep(30)
            
            # Verifica se ainda está na call (tenta obter o estado de voz)
            try:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('channel_id') != str(channel_id):
                            logger.warning("🔄 Reconectando à call...")
                            async with session.patch(url, headers=headers, json=payload) as reconnect:
                                if reconnect.status != 204:
                                    logger.error(f"❌ Falha ao reconectar: {reconnect.status}")
                    else:
                        logger.warning(f"⚠️ Não foi possível verificar estado: {resp.status}")
            except Exception as e:
                logger.error(f"❌ Erro no keepalive: {e}")

        # 6. Sai da call após o tempo
        try:
            async with session.patch(url, headers=headers, json={'channel_id': None}) as resp:
                if resp.status == 204:
                    logger.info("🔇 Desconectado da call após o tempo programado.")
        except Exception as e:
            logger.error(f"❌ Erro ao sair da call: {e}")

        # Remove a task
        if user_id in voice_tasks:
            del voice_tasks[user_id]

async def disconnect_user_voice(user_id: int):
    """Desconecta o usuário da call (apenas cancela a task)."""
    if user_id in voice_tasks:
        voice_tasks[user_id].cancel()
        del voice_tasks[user_id]
        return True
    return False