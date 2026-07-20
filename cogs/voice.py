import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import json
import socket
import struct
import random
import time
import aiohttp
from aiohttp import WSMsgType

from models.user import User
from utils.helpers import build_headers, request_with_rate_limit, fingerprint_mgr
from utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================
# CLASSE DE CONEXÃO DE VOZ (UDP)
# ============================================================
class VoiceConnection:
    def __init__(self, user_id, ws, token):
        self.user_id = user_id
        self.ws = ws
        self.token = token
        self.ssrc = random.randint(100000, 999999)
        self.sequence = 0
        self.timestamp = 0
        self.is_running = False
        self.udp_task = None
        self.voice_ip = None
        self.voice_port = None
        self.udp_socket = None
        self.loop = asyncio.get_running_loop()

    async def start(self):
        try:
            logger.info(f"[Voice][{self.user_id}] Aguardando op:2...")
            # Aguarda o evento op:2 (Ready) do voice WS
            while True:
                msg = await self.ws.receive()
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                data = json.loads(msg.data)
                op = data.get('op')
                if op == 2:
                    logger.info(f"[Voice][{self.user_id}] Recebido op:2")
                    break
                else:
                    logger.debug(f"[Voice][{self.user_id}] Ignorando op {op}")

            ip = data['d']['ip']
            port = data['d']['port']
            self.ssrc = data['d']['ssrc']
            modes = data['d']['modes']
            mode = modes[0] if modes else 'xsalsa20_poly1305'

            logger.info(f"[Voice][{self.user_id}] IP: {ip}, Port: {port}, SSRC: {self.ssrc}, Mode: {mode}")

            # Cria socket UDP não bloqueante
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setblocking(False)

            # Pacote de descoberta
            packet = bytearray(74)
            struct.pack_into('>H', packet, 0, 1)
            struct.pack_into('>H', packet, 2, 70)
            struct.pack_into('>I', packet, 4, self.ssrc)

            logger.info(f"[Voice][{self.user_id}] Enviando pacote UDP para {ip}:{port}")
            try:
                await self.loop.sock_sendto(self.udp_socket, packet, (ip, port))
            except Exception as e:
                logger.error(f"[Voice][{self.user_id}] Erro ao enviar UDP: {e}")
                return False

            # Aguarda resposta com timeout
            logger.info(f"[Voice][{self.user_id}] Aguardando resposta UDP (timeout 5s)...")
            try:
                resp, addr = await asyncio.wait_for(
                    self.loop.sock_recvfrom(self.udp_socket, 74),
                    timeout=5.0
                )
                logger.info(f"[Voice][{self.user_id}] Resposta recebida de {addr}")
            except asyncio.TimeoutError:
                logger.error(f"[Voice][{self.user_id}] Timeout aguardando resposta UDP")
                return False
            except Exception as e:
                logger.error(f"[Voice][{self.user_id}] Erro ao receber UDP: {e}")
                return False

            # Extrai IP e porta externos
            external_ip = resp[8:72].decode('utf-8').strip('\x00')
            external_port = struct.unpack_from('>H', resp, 72)[0]
            logger.info(f"[Voice][{self.user_id}] IP externo: {external_ip}, Porta externa: {external_port}")

            self.voice_ip = external_ip
            self.voice_port = external_port

            # Envia confirmação para o WS
            await self.ws.send(json.dumps({
                "op": 1,
                "d": {
                    "protocol": "udp",
                    "data": {
                        "address": external_ip,
                        "port": external_port,
                        "mode": mode
                    }
                }
            }))
            logger.info(f"[Voice][{self.user_id}] Confirmação enviada ao WS")

            self.is_running = True
            self.udp_task = asyncio.create_task(self._udp_heartbeat())
            logger.info(f"✅ Voice UDP iniciado para {self.user_id}")
            return True

        except Exception as e:
            logger.error(f"[Voice][{self.user_id}] ❌ Erro ao iniciar conexão de voz: {e}", exc_info=True)
            return False

    async def _udp_heartbeat(self):
        if not self.voice_ip or not self.voice_port:
            logger.warning(f"[Voice][{self.user_id}] Sem IP/porta para heartbeat")
            return
        while self.is_running and self.udp_socket:
            try:
                header = bytearray(12)
                header[0] = 0x80
                header[1] = 0x78
                struct.pack_into('>H', header, 2, self.sequence)
                struct.pack_into('>I', header, 4, self.timestamp)
                struct.pack_into('>I', header, 8, self.ssrc)
                self.sequence += 1
                self.timestamp += 960
                self.udp_socket.sendto(header, (self.voice_ip, self.voice_port))
            except Exception as e:
                logger.warning(f"[Voice][{self.user_id}] ⚠️ Erro no UDP heartbeat: {e}")
            await asyncio.sleep(random.uniform(4.0, 8.0))

    def stop(self):
        self.is_running = False
        if self.udp_task and not self.udp_task.done():
            self.udp_task.cancel()
        if self.udp_socket:
            try:
                self.udp_socket.close()
            except:
                pass

# ============================================================
# COG DE VOZ
# ============================================================
class Voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_calls = {}  # user_id -> task

    @app_commands.command(name='call', description='Entra em um canal de voz por um período')
    @app_commands.describe(
        channel_id='ID do canal de voz',
        hours='Tempo em horas (ex: 0.5 para 30 minutos)'
    )
    async def call(self, interaction: discord.Interaction, channel_id: str, hours: float):
        await interaction.response.defer()
        user = User(interaction.user.id)
        token = user.get_token()
        if not token:
            await interaction.followup.send("❌ Nenhum token configurado. Use `/add_token`.")
            return

        if interaction.user.id in self.active_calls:
            await interaction.followup.send("⏳ Você já tem uma call ativa. Use `/stop_call` para encerrar.")
            return

        try:
            channel_id = int(channel_id)
        except ValueError:
            await interaction.followup.send("❌ ID do canal inválido.")
            return

        if hours <= 0 or hours > 24:
            await interaction.followup.send("❌ Tempo inválido. Use entre 0.1 e 24 horas.")
            return

        msg = await interaction.followup.send(f"🔄 Conectando à call por {hours}h...")

        # Inicia a tarefa
        task = asyncio.create_task(self._perform_voice_farm(interaction.user.id, token, channel_id, hours, msg))
        self.active_calls[interaction.user.id] = task
        try:
            await task
        finally:
            self.active_calls.pop(interaction.user.id, None)

    @app_commands.command(name='stop_call', description='Encerra a call ativa')
    async def stop_call(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        if user_id not in self.active_calls:
            await interaction.response.send_message("❌ Você não tem uma call ativa.", ephemeral=True)
            return
        self.active_calls[user_id].cancel()
        await interaction.response.send_message("⏹️ Call encerrada.", ephemeral=True)

    async def _perform_voice_farm(self, user_id, token, channel_id, hours, progress_msg):
        headers = build_headers({"Authorization": token})

        async with aiohttp.ClientSession() as aio_session:
            # Obtém gateway
            try:
                async with aio_session.get("https://discord.com/api/v10/gateway") as resp_gw:
                    if resp_gw.status != 200:
                        raise Exception("Gateway API failed")
                    gw_data = await resp_gw.json()
                    gateway_url = gw_data['url'] + "?v=10&encoding=json"
                    logger.info(f"[Voice] Gateway URL obtido: {gateway_url}")
            except Exception as e:
                logger.warning(f"[Voice] Erro ao obter gateway: {e}, usando fallback")
                gateway_url = "wss://gateway.discord.gg/?v=10&encoding=json"

            # Obtém informações do canal
            resp = await request_with_rate_limit('GET', f'https://discord.com/api/v10/channels/{channel_id}', headers=headers)
            if resp.status_code != 200:
                await progress_msg.edit(content=f"❌ Erro ao acessar canal (status {resp.status_code})")
                return
            channel_data = resp.json()
            guild_id = channel_data.get('guild_id')
            if not guild_id:
                await progress_msg.edit(content="❌ Canal não pertence a um servidor de voz.")
                return

            try:
                voice_ws = await aio_session.ws_connect(gateway_url)
            except Exception as e:
                logger.error(f"[Voice] Erro ao conectar WS: {e}")
                await progress_msg.edit(content=f"❌ Erro ao conectar ao gateway: {e}")
                return

            try:
                hello = await voice_ws.receive_json()
                base_interval = hello['d']['heartbeat_interval'] / 1000.0

                await voice_ws.send_json({
                    "op": 2,
                    "d": {
                        "token": token,
                        "properties": fingerprint_mgr.get(vary=False)
                    }
                })
                # Aguarda ready
                while True:
                    msg = await voice_ws.receive_json()
                    if msg.get('op') == 0:
                        break

                await voice_ws.send_json({
                    "op": 4,
                    "d": {
                        "guild_id": guild_id,
                        "channel_id": str(channel_id),
                        "self_mute": True,
                        "self_deaf": True
                    }
                })

                voice = VoiceConnection(user_id, voice_ws, token)
                if not await voice.start():
                    await voice_ws.close()
                    await progress_msg.edit(content="❌ Falha ao estabelecer conexão UDP.")
                    return

                await progress_msg.edit(content=f"✅ Na call com RTP ativo por {hours}h")
                logger.info(f"📞 Usuário {user_id} entrou na call por {hours}h")

                end_time = time.time() + (hours * 3600)
                last_log = time.time()

                while time.time() < end_time:
                    if time.time() - last_log > 60:
                        remaining = max(0, int((end_time - time.time()) / 60))
                        await progress_msg.edit(content=f"🎧 Na call – faltam `{remaining}` minutos.")
                        last_log = time.time()

                    try:
                        msg = await asyncio.wait_for(voice_ws.receive(), timeout=60.0)
                        if msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                            logger.warning(f"WebSocket de voz fechado para {user_id}")
                            break
                    except asyncio.TimeoutError:
                        try:
                            await voice_ws.send_json({"op": 1, "d": None})
                        except:
                            break
                    except Exception as e:
                        logger.error(f"Erro no loop de voz: {e}")
                        break

                    await asyncio.sleep(1.0)

                voice.stop()
                await voice_ws.close()
                await progress_msg.edit(content="⏹️ Call encerrada.")
                logger.info(f"📞 Usuário {user_id} saiu da call.")

            except asyncio.CancelledError:
                voice.stop()
                await voice_ws.close()
                await progress_msg.edit(content="⏹️ Call interrompida pelo usuário.")
                raise
            except Exception as e:
                logger.error(f"Erro geral na voz: {e}", exc_info=True)
                await progress_msg.edit(content=f"❌ Erro: {str(e)[:100]}")
                await voice_ws.close()

# ============================================================
# SETUP (obrigatório para cogs)
# ============================================================
async def setup(bot):
    await bot.add_cog(Voice(bot))