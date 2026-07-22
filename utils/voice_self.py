import asyncio
import aiohttp
import logging
import json
import websockets
import struct
import socket
import time
import os

logger = logging.getLogger(__name__)

# Mapa de conexões ativas (user_id -> task)
active_voice_tasks = {}

async def get_gateway_url(token: str) -> str:
    """Obtém a URL do gateway de voz via API REST."""
    async with aiohttp.ClientSession() as session:
        headers = {'Authorization': token}
        async with session.get('https://discord.com/api/v9/gateway', headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data['url']
    return None

async def get_voice_websocket(token: str, guild_id: int, channel_id: int):
    """
    Obtém o endpoint e token de voz para o canal específico.
    Retorna (endpoint, token_voz, session_id, user_id).
    """
    # 1. Conecta ao Gateway principal para obter session_id
    gateway_url = await get_gateway_url(token)
    if not gateway_url:
        return None

    async with websockets.connect(f"{gateway_url}?v=10&encoding=json") as ws:
        # Recebe hello
        hello = json.loads(await ws.recv())
        heartbeat_interval = hello['d']['heartbeat_interval'] / 1000.0
        
        # Envia identify (self-bot)
        identify_payload = {
            "op": 2,
            "d": {
                "token": token,
                "intents": 1 << 9,  # GUILD_VOICE_STATES
                "properties": {
                    "os": "Windows",
                    "browser": "Chrome",
                    "device": ""
                }
            }
        }
        await ws.send(json.dumps(identify_payload))
        
        # Aguarda ready
        while True:
            msg = json.loads(await ws.recv())
            if msg['op'] == 0 and msg['t'] == 'READY':
                session_id = msg['d']['session_id']
                user_id = msg['d']['user']['id']
                break
        
        # Envia voice state update para entrar no canal
        voice_state_payload = {
            "op": 4,
            "d": {
                "guild_id": str(guild_id),
                "channel_id": str(channel_id),
                "self_mute": False,
                "self_deaf": False
            }
        }
        await ws.send(json.dumps(voice_state_payload))
        
        # Aguarda o servidor retornar o endpoint de voz
        voice_server = None
        while True:
            msg = json.loads(await ws.recv())
            if msg['op'] == 0 and msg['t'] == 'VOICE_SERVER_UPDATE':
                voice_server = msg['d']
                break
            if msg['op'] == 0 and msg['t'] == 'VOICE_STATE_UPDATE':
                # pode ignorar
                pass
        
        # Agora obtém o token de voz via API
        async with aiohttp.ClientSession() as session:
            headers = {'Authorization': token}
            async with session.get(f'https://discord.com/api/v9/channels/{channel_id}/voice', headers=headers) as resp:
                if resp.status == 200:
                    voice_data = await resp.json()
                    voice_token = voice_data['token']
                    endpoint = voice_server['endpoint']
                    return endpoint, voice_token, session_id, user_id
    return None

async def connect_udp(endpoint: str, voice_token: str, session_id: str, user_id: str, guild_id: int, channel_id: int):
    """
    Conecta via UDP ao servidor de voz.
    """
    # Parse endpoint (ex: "us-east-123.voice.discord.gg")
    host = endpoint.split(':')[0]
    port = 443  # padrão, mas pode variar
    
    # Obtém o IP via DNS
    try:
        import socket
        ip = socket.gethostbyname(host)
    except:
        ip = host
    
    # Conecta UDP
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5.0)
    
    # Monta o pacote de identificação (protocolo de voz do Discord)
    # Descrição do protocolo: https://discord.com/developers/docs/topics/voice-connections
    # Pacote de identificação: 70 bytes
    packet = bytearray(70)
    packet[0] = 0  # versão do protocolo (RTP)
    packet[1] = 0  # não usado
    # SSRC: 32 bits (precisa ser único)
    import random
    ssrc = random.randint(100000, 999999)
    struct.pack_into('>I', packet, 8, ssrc)
    # User ID (64 bits)
    struct.pack_into('>Q', packet, 12, int(user_id))
    # Guild ID (64 bits)
    struct.pack_into('>Q', packet, 20, int(guild_id))
    # Channel ID (64 bits)
    struct.pack_into('>Q', packet, 28, int(channel_id))
    # Session ID (32 bytes)
    session_bytes = session_id.encode('utf-8')[:32]
    packet[36:36+len(session_bytes)] = session_bytes
    # Token de voz (até 32 bytes)
    token_bytes = voice_token.encode('utf-8')[:32]
    packet[68:68+len(token_bytes)] = token_bytes
    
    # Envia o pacote de identificação
    sock.sendto(bytes(packet), (ip, port))
    
    # Aguarda resposta (pacote de ready)
    try:
        data, addr = sock.recvfrom(1024)
        # A resposta contém o IP e porta do servidor para envio de áudio
        # Vamos extrair o IP e porta (formato: 8 bytes IP, 2 bytes porta)
        server_ip = socket.inet_ntoa(data[8:12])  # 4 bytes
        server_port = struct.unpack('>H', data[12:14])[0]  # 2 bytes
        logger.info(f"✅ Conectado ao servidor de voz {server_ip}:{server_port}")
        
        # Agora ficamos em loop enviando pacotes de silêncio (RTP)
        # Pacote de silêncio: cabeçalho RTP (12 bytes) + payload vazio
        rtp_packet = bytearray(12)
        # Versão 2, padding 0, extension 0, CSRC count 0
        rtp_packet[0] = 0x80
        # Payload type: 0x78 (120) para PCMU (ou 0x7a para silêncio)
        rtp_packet[1] = 0x78
        # Timestamp (aumenta a cada 20ms)
        timestamp = 0
        # SSRC (mesmo do início)
        struct.pack_into('>I', rtp_packet, 8, ssrc)
        
        # Envia pacotes de silêncio a cada 20ms (para manter conexão)
        start_time = time.time()
        while True:
            # Atualiza timestamp (incrementa 960 a cada 20ms = 48kHz)
            struct.pack_into('>I', rtp_packet, 4, timestamp)
            timestamp += 960
            sock.sendto(bytes(rtp_packet), (server_ip, server_port))
            await asyncio.sleep(0.02)  # 20ms
            
            # Verifica se deve parar (a task será cancelada externamente)
            if asyncio.current_task().cancelled():
                break
    except Exception as e:
        logger.error(f"❌ Erro no UDP: {e}")
    finally:
        sock.close()

async def connect_user_voice_self(token: str, guild_id: int, channel_id: int, hours: int, user_id: int):
    """
    Função principal para conectar a conta do usuário na call usando WebSocket + UDP.
    """
    try:
        endpoint, voice_token, session_id, user_id = await get_voice_websocket(token, guild_id, channel_id)
        if not endpoint:
            logger.error("❌ Não foi possível obter dados de voz")
            return
        
        logger.info(f"🔊 Conectando à call: {endpoint}")
        await connect_udp(endpoint, voice_token, session_id, user_id, guild_id, channel_id)
        
    except asyncio.CancelledError:
        logger.info("🔇 Task de voz cancelada")
    except Exception as e:
        logger.error(f"❌ Erro na conexão de voz self: {e}")