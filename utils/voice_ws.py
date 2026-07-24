import asyncio
import aiohttp
import websockets
import socket
import json
import logging
import time
import struct
import random

logger = logging.getLogger(__name__)

OP_HELLO = 0
OP_IDENTIFY = 1
OP_SELECT_PROTOCOL = 2
OP_READY = 3
OP_HEARTBEAT = 4
OP_SESSION_DESCRIPTION = 5
OP_HEARTBEAT_ACK = 7

class VoiceWSClient:
    def __init__(self, token: str, guild_id: int, channel_id: int, user_id: str):
        self.token = token
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.user_id = user_id
        self.session_id = None
        self.voice_token = None
        self.endpoint = None
        self.voice_ws = None
        self.udp_socket = None
        self.udp_ip = None
        self.udp_port = None
        self.udp_ssrc = random.randint(1, 2**32 - 1)
        self.is_running = False
        self.heartbeat_interval = 15

    async def run(self):
        self.is_running = True
        try:
            await self._connect_gateway()
            if self.voice_token and self.endpoint:
                await self._connect_voice_gateway()
                await self._udp_handshake()
                await self._keep_alive()
        except asyncio.CancelledError:
            logger.info("Task de voz cancelada.")
            raise
        except Exception as e:
            logger.error(f"Erro no VoiceWS: {e}")
        finally:
            await self.cleanup()

    async def _connect_gateway(self):
        headers = {'Authorization': self.token}
        async with aiohttp.ClientSession() as session:
            async with session.get('https://discord.com/api/v9/gateway') as resp:
                data = await resp.json()
                gateway_url = data.get('url', 'wss://gateway.discord.gg/') + '?v=9&encoding=json'

            async with websockets.connect(gateway_url) as ws:
                hello_msg = json.loads(await ws.recv())
                self.heartbeat_interval = hello_msg['d']['heartbeat_interval'] / 1000

                identify_payload = {
                    'op': OP_IDENTIFY,
                    'd': {
                        'token': self.token,
                        'intents': 1 << 9,
                        'properties': {'os': 'Linux', 'browser': 'Chrome', 'device': 'PC'}
                    }
                }
                await ws.send(json.dumps(identify_payload))

                voice_state_payload = {
                    'op': 4,
                    'd': {
                        'guild_id': str(self.guild_id),
                        'channel_id': str(self.channel_id),
                        'self_mute': False,
                        'self_deaf': False
                    }
                }
                await ws.send(json.dumps(voice_state_payload))

                timeout = 0
                while timeout < 30:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        data = json.loads(msg)
                        t = data.get('t')
                        
                        if t == 'READY':
                            self.session_id = data['d']['session_id']
                        elif t == 'VOICE_STATE_UPDATE':
                            d = data.get('d', {})
                            if d.get('user_id') == str(self.user_id):
                                self.session_id = d.get('session_id')
                        elif t == 'VOICE_SERVER_UPDATE':
                            d = data.get('d', {})
                            if d.get('guild_id') == str(self.guild_id):
                                self.voice_token = d.get('token')
                                endpoint_raw = d.get('endpoint')
                                if endpoint_raw:
                                    self.endpoint = endpoint_raw.split(':')[0]
                        
                        if self.session_id and self.voice_token and self.endpoint:
                            break 
                    except asyncio.TimeoutError:
                        timeout += 5

    async def _connect_voice_gateway(self):
        ws_url = f"wss://{self.endpoint}/?v=4"
        self.voice_ws = await websockets.connect(ws_url)
        await self.voice_ws.recv() 
        
        identify = {
            'op': OP_IDENTIFY,
            'd': {
                'server_id': str(self.guild_id),
                'user_id': str(self.user_id),
                'session_id': self.session_id,
                'token': self.voice_token
            }
        }
        await self.voice_ws.send(json.dumps(identify))
        
        ready_msg = json.loads(await self.voice_ws.recv())
        d = ready_msg.get('d', {})
        self.udp_ip = d.get('ip')
        self.udp_port = d.get('port')
        self.udp_ssrc = d.get('ssrc', self.udp_ssrc)

    async def _udp_handshake(self):
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setblocking(False)

        discovery_packet = bytearray(74)
        struct.pack_into('>H', discovery_packet, 0, 1)
        struct.pack_into('>H', discovery_packet, 2, 70)
        struct.pack_into('>I', discovery_packet, 4, self.udp_ssrc)
        
        self.udp_socket.sendto(discovery_packet, (self.udp_ip, self.udp_port))

        loop = asyncio.get_running_loop()
        response, _ = await asyncio.wait_for(loop.sock_recv(self.udp_socket, 1024), timeout=5.0)

        ip_end = response.find(b'\x00', 8)
        ip = response[8:ip_end].decode('utf-8')
        port = struct.unpack('>H', response[-2:])[0]

        select_payload = {
            'op': OP_SELECT_PROTOCOL,
            'd': {
                'protocol': 'udp',
                'data': {'address': ip, 'port': port, 'mode': 'xsalsa20_poly1305'}
            }
        }
        await self.voice_ws.send(json.dumps(select_payload))
        await self.voice_ws.recv() 

    async def _keep_alive(self):
        logger.info(f"🎧 Conectado à call {self.channel_id} com sucesso.")
        while self.is_running:
            await asyncio.sleep(self.heartbeat_interval)
            if self.voice_ws:
                try:
                    await self.voice_ws.send(json.dumps({'op': OP_HEARTBEAT, 'd': int(time.time() * 1000)}))
                except:
                    break

    async def cleanup(self):
        self.is_running = False
        if self.voice_ws: await self.voice_ws.close()
        if self.udp_socket: self.udp_socket.close()
        logger.info("🔇 Desconectado da call.")

async def start_voice_task(token: str, guild_id: int, channel_id: int, user_id: str):
    client = VoiceWSClient(token, guild_id, channel_id, user_id)
    await client.run()
