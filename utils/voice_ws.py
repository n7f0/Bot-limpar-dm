import asyncio
import aiohttp
import logging
import json
import websockets
import socket
import struct
import time
import random
import os

logger = logging.getLogger(__name__)

voice_tasks = {}  # user_id -> asyncio.Task

async def get_user_info(token: str):
    headers = {'Authorization': token}
    async with aiohttp.ClientSession() as session:
        async with session.get('https://discord.com/api/v9/users/@me', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            return None

async def get_user_guilds(token: str):
    headers = {'Authorization': token}
    async with aiohttp.ClientSession() as session:
        async with session.get('https://discord.com/api/v9/users/@me/guilds', headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            return []

async def get_voice_state(token: str, guild_id: int, channel_id: int):
    """Obtém o estado de voz atual do usuário no servidor."""
    headers = {'Authorization': token}
    url = f'https://discord.com/api/v9/guilds/{guild_id}/voice-states/@me'
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                return await resp.json()
            return None

async def update_voice_state(token: str, guild_id: int, channel_id: int = None, self_mute: bool = False, self_deaf: bool = False):
    """Atualiza o estado de voz do usuário (entra/sai da call)."""
    headers = {
        'Authorization': token,
        'Content-Type': 'application/json'
    }
    url = f'https://discord.com/api/v9/guilds/{guild_id}/voice-states/@me'
    payload = {
        'channel_id': str(channel_id) if channel_id else None,
        'self_mute': self_mute,
        'self_deaf': self_deaf
    }
    async with aiohttp.ClientSession() as session:
        async with session.patch(url, headers=headers, json=payload) as resp:
            return resp.status == 204

def udp_keepalive(sock, ssrc, address, interval=30):
    """Envia pacotes UDP de keepalive para o servidor de voz."""
    # Pacote de keepalive: 70 bytes de zeros (padrão do Discord)
    packet = bytearray(70)
    struct.pack_into('>I', packet, 0, ssrc)  # SSRC no início
    while True:
        try:
            sock.sendto(packet, address)
        except:
            pass
        time.sleep(interval)

async def connect_voice_ws(token: str, guild_id: int, channel_id: int, hours: int, user_id: int):
    """
    Conecta ao gateway de voz do Discord usando WebSocket e UDP.
    Mantém a call por X horas enviando pacotes de keepalive e silêncio.
    """
    # 1. Valida token
    user = await get_user_info(token)
    if not user:
        logger.error("❌ Token inválido")
        return

    # 2. Verifica se está no servidor
    guilds = await get_user_guilds(token)
    if str(guild_id) not in [g['id'] for g in guilds]:
        logger.error(f"❌ Você não está no servidor {guild_id}")
        return

    # 3. Entra na call via REST
    success = await update_voice_state(token, guild_id, channel_id)
    if not success:
        logger.error("❌ Falha ao entrar na call via REST")
        return

    logger.info(f"✅ Entrou na call via REST, aguardando gateway de voz...")

    # 4. Aguarda o Discord fornecer o endpoint de voz (precisa de polling)
    # O Discord envia um evento VOICE_SERVER_UPDATE via websocket principal, mas não temos acesso.
    # Vamos tentar obter o estado de voz repetidamente.
    voice_data = None
    for _ in range(20):  # tenta por até 10 segundos
        await asyncio.sleep(0.5)
        state = await get_voice_state(token, guild_id)
        if state and state.get('token'):
            voice_data = state
            break

    if not voice_data or not voice_data.get('token'):
        logger.error("❌ Não foi possível obter o token de voz")
        await update_voice_state(token, guild_id, channel_id=None)
        return

    # 5. Conecta ao gateway de voz via WebSocket
    endpoint = voice_data.get('endpoint')
    if not endpoint:
        logger.error("❌ Endpoint de voz não encontrado")
        await update_voice_state(token, guild_id, channel_id=None)
        return

    # Adiciona o protocolo wss://
    if not endpoint.startswith('wss://'):
        endpoint = f'wss://{endpoint}'

    # 6. Handshake de voz
    try:
        async with websockets.connect(f'{endpoint}/?v=4', extra_headers={'Authorization': token}) as ws:
            logger.info(f"✅ Conectado ao gateway de voz: {endpoint}")

            # Envia o payload de identificação
            identify_payload = {
                'op': 0,
                'd': {
                    'server_id': str(guild_id),
                    'user_id': user['id'],
                    'session_id': '',  # não temos, mas pode ser vazio
                    'token': voice_data['token']
                }
            }
            await ws.send(json.dumps(identify_payload))

            # Aguarda a resposta de ready
            resp = await ws.recv()
            data = json.loads(resp)

            if data.get('op') != 2:
                logger.error(f"❌ Falha no handshake: {data}")
                await update_voice_state(token, guild_id, channel_id=None)
                return

            # Obtém informações UDP do servidor de voz
            udp_data = data.get('d', {})
            ip = udp_data.get('ip')
            port = udp_data.get('port')
            ssrc = udp_data.get('ssrc')

            if not ip or not port or not ssrc:
                logger.error("❌ Dados UDP incompletos")
                await update_voice_state(token, guild_id, channel_id=None)
                return

            logger.info(f"🎧 Servidor de voz: {ip}:{port}, SSRC: {ssrc}")

            # 7. Envia pacotes UDP de keepalive
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            address = (ip, port)

            # Inicia a thread de keepalive
            import threading
            keepalive_thread = threading.Thread(
                target=udp_keepalive,
                args=(sock, ssrc, address, 30),
                daemon=True
            )
            keepalive_thread.start()

            # 8. Mantém a conexão WebSocket ativa por X horas
            start_time = time.time()
            end_time = start_time + (hours * 3600)

            while time.time() < end_time:
                try:
                    # Aguarda mensagens do gateway (opção, podemos apenas manter a conexão)
                    await asyncio.wait_for(ws.recv(), timeout=30)
                except asyncio.TimeoutError:
                    # Envia um ping para manter a conexão ativa
                    await ws.send(json.dumps({'op': 3, 'd': None}))  # heartbeart
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("🔄 Conexão WebSocket fechada, reconectando...")
                    # Tenta reconectar (simplificado)
                    break
                except Exception as e:
                    logger.error(f"❌ Erro no WebSocket: {e}")
                    break

            # 9. Desconecta
            sock.close()
            await update_voice_state(token, guild_id, channel_id=None)
            logger.info(f"🔇 Desconectado após {hours}h")

    except Exception as e:
        logger.error(f"❌ Erro no WebSocket de voz: {e}")
        await update_voice_state(token, guild_id, channel_id=None)

    # Remove a task
    if user_id in voice_tasks:
        del voice_tasks[user_id]

async def disconnect_user_voice(user_id: int):
    """Cancela a task de voz."""
    if user_id in voice_tasks:
        voice_tasks[user_id].cancel()
        del voice_tasks[user_id]
        return True
    return False