import asyncio
import aiohttp
import websockets
import socket
import json
import logging
import time
import nacl.secret
import nacl.utils
import nacl.public
import nacl.encoding
import os
import struct
import base64
import random
import threading
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# ============================================================
# CONSTANTES
# ============================================================
VOICE_GATEWAY_VERSION = 4
OP_HELLO = 0
OP_IDENTIFY = 1
OP_SELECT_PROTOCOL = 2
OP_READY = 3
OP_HEARTBEAT = 4
OP_SESSION_DESCRIPTION = 5
OP_SPEAKING = 6
OP_HEARTBEAT_ACK = 7
OP_RESUME = 8
OP_CLIENT_CONNECT = 9
OP_CLIENT_DISCONNECT = 10

# ============================================================
# CLASSE PRINCIPAL
# ============================================================
class VoiceWSClient:
    def __init__(self, token: str, guild_id: int, channel_id: int, hours: int, user_id: int):
        self.token = token
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.hours = hours
        self.user_id = user_id
        self.gateway_url = None
        self.session_id = None
        self.voice_server = None
        self.voice_token = None
        self.endpoint = None
        self.voice_ws = None
        self.udp_socket = None
        self.udp_ip = None
        self.udp_port = None
        self.udp_ssrc = random.randint(1, 2**32 - 1)
        self.udp_secret_key = None
        self.voice_conn = None
        self.is_running = False
        self.heartbeat_interval = 15
        self.last_heartbeat = 0

    async def run(self):
        """Ponto de entrada principal."""
        self.is_running = True
        try:
            # 1. Conecta ao gateway principal e obtém dados de voz
            await self._connect_gateway()
            if not self.voice_server or not self.voice_token or not self.endpoint:
                logger.error("❌ Dados de voz não recebidos")
                return

            # 2. Conecta ao gateway de voz
            await self._connect_voice_gateway()
            if not self.voice_ws:
                return

            # 3. Handshake UDP
            await self._udp_handshake()

            # 4. Mantém conexão por X horas
            await self._keep_alive()

        except Exception as e:
            logger.error(f"❌ Erro no VoiceWSClient: {e}")
        finally:
            await self.cleanup()

    # ============================================================
    # 1. GATEWAY PRINCIPAL (para obter voz)
    # ============================================================
    async def _connect_gateway(self):
        """Conecta ao gateway principal para receber eventos de voz."""
        headers = {'Authorization': self.token}
        async with aiohttp.ClientSession() as session:
            # Obtém URL do gateway
            async with session.get('https://discord.com/api/v9/gateway') as resp:
                if resp.status != 200:
                    logger.error(f"❌ Falha ao obter gateway: {resp.status}")
                    return
                data = await resp.json()
                gateway_url = data.get('url', 'wss://gateway.discord.gg/')
                gateway_url += '?v=9&encoding=json'

            # Conecta via WebSocket
            async with websockets.connect(gateway_url) as ws:
                # Aguarda HELLO
                hello_msg = json.loads(await ws.recv())
                if hello_msg.get('op') != OP_HELLO:
                    logger.error("❌ HELLO não recebido")
                    return
                self.heartbeat_interval = hello_msg['d']['heartbeat_interval'] / 1000

                # Envia IDENTIFY
                identify_payload = {
                    'op': OP_IDENTIFY,
                    'd': {
                        'token': self.token,
                        'intents': 1 << 9,  # GUILD_VOICE_STATES
                        'properties': {
                            'os': 'Linux',
                            'browser': 'Chrome',
                            'device': 'SelfBot'
                        }
                    }
                }
                await ws.send(json.dumps(identify_payload))

                # Escuta eventos até receber VOICE_STATE_UPDATE e VOICE_SERVER_UPDATE
                while True:
                    message = await ws.recv()
                    data = json.loads(message)

                    # Heartbeat
                    if data.get('op') == OP_HEARTBEAT_ACK:
                        continue

                    # Ready
                    if data.get('t') == 'READY':
                        self.session_id = data['d']['session_id']
                        logger.info(f"✅ Session ID: {self.session_id}")

                    # VOICE_STATE_UPDATE (guarda a session_id)
                    elif data.get('t') == 'VOICE_STATE_UPDATE':
                        d = data.get('d', {})
                        if d.get('user_id') == self.user_id:
                            self.session_id = d.get('session_id')
                            logger.info(f"✅ Session ID (atualizado): {self.session_id}")

                    # VOICE_SERVER_UPDATE (guarda endpoint e token)
                    elif data.get('t') == 'VOICE_SERVER_UPDATE':
                        d = data.get('d', {})
                        if d.get('guild_id') == str(self.guild_id):
                            self.voice_token = d.get('token')
                            self.endpoint = d.get('endpoint')
                            logger.info(f"✅ Endpoint de voz: {self.endpoint}")
                            # Sai do loop quando tiver dados completos
                            if self.voice_token and self.endpoint and self.session_id:
                                break

                    # Se já temos tudo, pode parar
                    if self.voice_token and self.endpoint and self.session_id:
                        break

                # Encerra a conexão com o gateway principal
                await ws.close()
                logger.info("✅ Gateway principal desconectado")

    # ============================================================
    # 2. GATEWAY DE VOZ
    # ============================================================
    async def _connect_voice_gateway(self):
        """Conecta ao gateway de voz."""
        if not self.endpoint:
            logger.error("❌ Endpoint de voz não disponível")
            return

        # Endpoint vem com porta, ex: "us-east-1.discord.gg"
        ws_url = f"wss://{self.endpoint}/?v={VOICE_GATEWAY_VERSION}"
        try:
            self.voice_ws = await websockets.connect(ws_url)
            logger.info(f"✅ Conectado ao gateway de voz: {ws_url}")

            # Aguarda HELLO do voice
            hello_msg = json.loads(await self.voice_ws.recv())
            if hello_msg.get('op') != OP_HELLO:
                logger.error("❌ HELLO não recebido do voice gateway")
                return

            # Envia IDENTIFY do voice
            voice_identify = {
                'op': OP_IDENTIFY,
                'd': {
                    'server_id': str(self.guild_id),
                    'user_id': str(self.user_id),
                    'session_id': self.session_id,
                    'token': self.voice_token
                }
            }
            await self.voice_ws.send(json.dumps(voice_identify))
            logger.info("✅ Identify enviado para gateway de voz")

            # Aguarda READY
            ready_msg = json.loads(await self.voice_ws.recv())
            if ready_msg.get('op') != OP_READY:
                logger.error("❌ READY não recebido do voice gateway")
                return

            # Extrai dados do UDP
            d = ready_msg.get('d', {})
            self.udp_ip = d.get('ip')
            self.udp_port = d.get('port')
            self.udp_ssrc = d.get('ssrc', self.udp_ssrc)
            self.udp_secret_key = d.get('secret_key')  # array de bytes?
            logger.info(f"✅ UDP IP: {self.udp_ip}, Porta: {self.udp_port}, SSRC: {self.udp_ssrc}")

        except Exception as e:
            logger.error(f"❌ Erro ao conectar ao gateway de voz: {e}")
            self.voice_ws = None

    # ============================================================
    # 3. HANDSHAKE UDP
    # ============================================================
    async def _udp_handshake(self):
        """Realiza o handshake UDP com o servidor de voz."""
        if not self.udp_ip or not self.udp_port:
            logger.error("❌ Dados UDP não disponíveis")
            return

        try:
            # Cria socket UDP
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setblocking(False)
            self.udp_socket.settimeout(5.0)

            # Envia pacote de descoberta (Discovery)
            # Formato: [SSRC (4 bytes), 0x00000000 (4 bytes), 0x00000000 (4 bytes), 0x00000000 (4 bytes)]
            discovery_packet = struct.pack('>IIII', self.udp_ssrc, 0, 0, 0)
            self.udp_socket.sendto(discovery_packet, (self.udp_ip, self.udp_port))

            # Recebe resposta
            response, addr = self.udp_socket.recvfrom(1024)
            # Resposta: [IP (string), Porta (unsigned short), SSRC]
            # Formato: primeiro 4 bytes = endereço IP
            ip = response[4:].decode('utf-8').split('\x00')[0]
            port = struct.unpack('>H', response[2:4])[0] if len(response) > 4 else self.udp_port
            ssrc = struct.unpack('>I', response[:4])[0] if len(response) >= 4 else self.udp_ssrc

            logger.info(f"✅ UDP handshake concluído: IP={ip}, Porta={port}, SSRC={ssrc}")

            # Envia SELECT_PROTOCOL para o gateway de voz
            select_payload = {
                'op': OP_SELECT_PROTOCOL,
                'd': {
                    'protocol': 'udp',
                    'data': {
                        'address': ip,
                        'port': port,
                        'mode': 'xsalsa20_poly1305'  # modo de criptografia
                    }
                }
            }
            await self.voice_ws.send(json.dumps(select_payload))
            logger.info("✅ SELECT_PROTOCOL enviado")

            # Aguarda SESSION_DESCRIPTION
            session_desc = json.loads(await self.voice_ws.recv())
            if session_desc.get('op') != OP_SESSION_DESCRIPTION:
                logger.error("❌ SESSION_DESCRIPTION não recebido")
                return

            # Extrai a chave de criptografia
            secret_key = session_desc['d']['secret_key']
            self.udp_secret_key = bytes(secret_key)
            logger.info(f"✅ Chave secreta recebida (tamanho: {len(self.udp_secret_key)})")

            # Inicia o envio de heartbeat UDP
            asyncio.create_task(self._udp_heartbeat())

        except Exception as e:
            logger.error(f"❌ Erro no handshake UDP: {e}")
            self.udp_socket = None

    # ============================================================
    # 4. HEARTBEAT UDP
    # ============================================================
    async def _udp_heartbeat(self):
        """Envia pacotes de heartbeat via UDP para manter a conexão."""
        if not self.udp_socket:
            return

        # Pacote de heartbeat: [SSRC (4 bytes), timestamp (8 bytes), sequência (2 bytes)]
        seq = 0
        while self.is_running:
            try:
                # Timestamp atual (em milissegundos, 48 bits)
                timestamp = int(time.time() * 1000) & 0xFFFFFFFFFFFF
                packet = struct.pack('>IQH', self.udp_ssrc, timestamp, seq)
                self.udp_socket.sendto(packet, (self.udp_ip, self.udp_port))
                seq = (seq + 1) % 65536
                await asyncio.sleep(5)  # a cada 5 segundos
            except Exception as e:
                logger.error(f"❌ Erro no heartbeat UDP: {e}")
                break

    # ============================================================
    # 5. KEEP ALIVE (principal)
    # ============================================================
    async def _keep_alive(self):
        """Mantém a conexão viva por X horas."""
        if not self.voice_ws:
            return

        logger.info(f"🎧 Conectado e mantendo call por {self.hours}h")
        start_time = time.time()
        end_time = start_time + (self.hours * 3600)

        # Heartbeat do WebSocket
        async def ws_heartbeat():
            while self.is_running:
                await asyncio.sleep(self.heartbeat_interval)
                if self.voice_ws:
                    try:
                        await self.voice_ws.send(json.dumps({'op': OP_HEARTBEAT, 'd': int(time.time() * 1000)}))
                    except:
                        pass

        # Inicia o heartbeat do WS
        hb_task = asyncio.create_task(ws_heartbeat())

        # Loop principal
        while self.is_running and time.time() < end_time:
            await asyncio.sleep(10)
            # Verifica se ainda está conectado
            if not self.voice_ws or self.voice_ws.closed:
                logger.warning("🔄 Conexão WebSocket perdida, tentando reconectar...")
                await self._reconnect_voice()
                # Reseta o contador se reconectou
                start_time = time.time()
                end_time = start_time + (self.hours * 3600)

        # Finaliza
        hb_task.cancel()
        logger.info("🔇 Tempo esgotado, desconectando...")
        await self.cleanup()

    async def _reconnect_voice(self):
        """Tenta reconectar ao gateway de voz."""
        try:
            await self._connect_voice_gateway()
            if self.voice_ws:
                await self._udp_handshake()
                logger.info("✅ Reconectado com sucesso")
        except Exception as e:
            logger.error(f"❌ Falha na reconexão: {e}")

    # ============================================================
    # 6. LIMPEZA
    # ============================================================
    async def cleanup(self):
        """Limpa todos os recursos."""
        self.is_running = False
        if self.voice_ws:
            await self.voice_ws.close()
            self.voice_ws = None
        if self.udp_socket:
            self.udp_socket.close()
            self.udp_socket = None
        logger.info("✅ Recursos liberados")

    # ============================================================
    # 7. DESCONEXÃO FORÇADA
    # ============================================================
    async def disconnect(self):
        """Desconecta a call imediatamente."""
        await self.cleanup()


# ============================================================
# FUNÇÕES PÚBLICAS PARA O PAINEL
# ============================================================
voice_tasks = {}  # user_id -> asyncio.Task

async def join_voice_websocket(token: str, guild_id: int, channel_id: int, hours: int, user_id: int):
    """
    Entra em call usando self-bot via WebSocket + UDP.
    Mantém a conexão por X horas.
    """
    # Obtém o ID do usuário a partir do token
    user_id_from_token = await _get_user_id(token)
    if not user_id_from_token:
        logger.error("❌ Não foi possível obter o ID do usuário")
        return

    client = VoiceWSClient(token, guild_id, channel_id, hours, user_id_from_token)
    await client.run()

async def _get_user_id(token: str) -> Optional[str]:
    """Obtém o ID do usuário a partir do token."""
    headers = {'Authorization': token}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get('https://discord.com/api/v9/users/@me', headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data['id']
        except:
            pass
    return None

async def disconnect_user_voice(user_id: int):
    """Desconecta o self-bot da call."""
    if user_id in voice_tasks:
        task = voice_tasks[user_id]
        task.cancel()
        del voice_tasks[user_id]
        logger.info(f"🔇 Desconectado para usuário {user_id}")
        return True
    return False