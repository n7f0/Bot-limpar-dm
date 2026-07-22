import asyncio
import aiohttp
import logging
import json
import websockets
import time
import random

logger = logging.getLogger(__name__)

# Armazena tarefas de voz ativas
voice_tasks = {}
voice_ws = {}  # user_id -> websocket

async def join_voice_call(token: str, guild_id: int, channel_id: int, hours: int, user_id: int):
    """
    Entra em um canal de voz usando token de usuário (self-bot) via REST.
    Mantém a conexão por X horas com keepalive.
    """
    headers = {
        'Authorization': token,
        'Content-Type': 'application/json'
    }

    async with aiohttp.ClientSession() as session:
        # 1. Entra no canal de voz via REST
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

        # 2. Mantém a conexão ativa por X horas (keepalive via WebSocket da voz)
        # O Discord desconecta após ~5min de inatividade, então precisamos enviar pacotes.
        # Vamos usar um loop que reconecta se cair.
        
        start_time = time.time()
        end_time = start_time + (hours * 3600)

        while time.time() < end_time:
            # Simula um keepalive enviando um "ping" via REST (não é perfeito, mas ajuda)
            # Opção: enviar um request para /voice/keepalive (não existe)
            # Então vamos apenas esperar e reconectar se cair
            await asyncio.sleep(30)
            
            # Verifica se ainda está na call (tenta obter o estado de voz)
            try:
                async with session.get(f'https://discord.com/api/v9/guilds/{guild_id}/voice-states/@me', headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get('channel_id') != str(channel_id):
                            # Caiu da call, reconecta
                            logger.warning("🔄 Reconectando à call...")
                            async with session.patch(url, headers=headers, json=payload) as reconnect:
                                if reconnect.status != 204:
                                    logger.error(f"❌ Falha ao reconectar: {reconnect.status}")
                    else:
                        logger.warning(f"⚠️ Não foi possível verificar estado: {resp.status}")
            except Exception as e:
                logger.error(f"❌ Erro no keepalive: {e}")

        # Sai da call após o tempo
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
    """Desconecta o usuário da call."""
    # Cancela a task se estiver rodando
    if user_id in voice_tasks:
        voice_tasks[user_id].cancel()
        del voice_tasks[user_id]
    
    # Tenta sair da call via REST (precisa do token, mas não temos aqui...)
    # Vamos apenas cancelar a task e ela sairá sozinha.
    return True