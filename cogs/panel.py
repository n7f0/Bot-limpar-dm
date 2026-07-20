import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import io
import base64
import json
import time
import socket
import struct
import random
import aiohttp
from aiohttp import WSMsgType

from models.user import User
from utils.helpers import (
    build_headers, request_with_rate_limit, generate_snowflake,
    normal_random, exponential_random, fingerprint_mgr
)
from utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================
# CONSTANTES DE SEGURANÇA
# ============================================================
MAX_MESSAGES = 150
MAX_BACKUP = 3000
MIN_DELAY = 15.0
MAX_DELAY = 35.0
PAUSE_AFTER = 20
PAUSE_DUR_MIN = 120.0
PAUSE_DUR_MAX = 180.0

# ============================================================
# CLASSE VOICE CONNECTION (UDP)
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

            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setblocking(False)

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

            external_ip = resp[8:72].decode('utf-8').strip('\x00')
            external_port = struct.unpack_from('>H', resp, 72)[0]
            logger.info(f"[Voice][{self.user_id}] IP externo: {external_ip}, Porta externa: {external_port}")

            self.voice_ip = external_ip
            self.voice_port = external_port

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
# COG PRINCIPAL – PAINEL
# ============================================================
class Panel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_tasks = {}

    @app_commands.command(name='painel', description='Abre o painel de controle completo')
    async def painel(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user = User(interaction.user.id)
        embed = self._build_dashboard_embed(user)
        view = DashboardView(user, self)
        await interaction.followup.send(embed=embed, view=view)

    def _build_dashboard_embed(self, user):
        tokens = user.data.get('tokens', [])
        default_idx = user.data.get('default_token_index', 0)
        chat_id = user.data.get('chat_id')
        farm_chat_id = user.data.get('farm_chat_id')
        farm_msg = user.data.get('farm_message', '')
        auto_farm = user.data.get('auto_farming', 0)
        embed = discord.Embed(title="🛡️ Nexzy Pro - Painel", color=discord.Color.blue())
        embed.add_field(name="Tokens", value=f"{len(tokens)} configurados", inline=True)
        embed.add_field(name="Token ativo", value=f"#{default_idx+1}" if tokens else "Nenhum", inline=True)
        embed.add_field(name="Canal (Limpeza/Backup)", value=f"<#{chat_id}>" if chat_id else "Não definido", inline=False)
        embed.add_field(name="Canal Farm", value=f"<#{farm_chat_id}>" if farm_chat_id else "Não definido", inline=False)
        embed.add_field(name="Mensagem Farm", value=farm_msg[:50] + "..." if len(farm_msg) > 50 else farm_msg or "Não definida", inline=False)
        embed.add_field(name="Auto-Farm", value="✅ Ativo" if auto_farm else "❌ Inativo", inline=True)
        embed.set_footer(text="Clique nos botões para executar ações")
        return embed

    async def _perform_cleanup(self, user_id, token, chat_id, limit, progress_msg, cancel_event):
        headers = build_headers({"Authorization": token})
        deleted = 0
        last_id = None
        while deleted < limit:
            if cancel_event.is_set():
                raise asyncio.CancelledError()
            url = f"https://discord.com/api/v10/channels/{chat_id}/messages?limit=100"
            if last_id:
                url += f"&before={last_id}"
            resp = await request_with_rate_limit('GET', url, headers=headers)
            if resp.status_code != 200:
                break
            msgs = resp.json()
            if not msgs:
                break
            for msg in msgs:
                if cancel_event.is_set():
                    raise asyncio.CancelledError()
                if msg['author']['id'] != str(user_id):
                    continue
                del_url = f"https://discord.com/api/v10/channels/{chat_id}/messages/{msg['id']}"
                del_resp = await request_with_rate_limit('DELETE', del_url, headers=headers)
                if del_resp.status_code == 204:
                    deleted += 1
                    if deleted % PAUSE_AFTER == 0:
                        pausa = random.uniform(PAUSE_DUR_MIN, PAUSE_DUR_MAX) + exponential_random(30, 0, 60)
                        await progress_msg.edit(content=f"⏸️ Pausa humana... {int(pausa)}s.")
                        await asyncio.sleep(pausa)
                    elif deleted % 3 == 0:
                        await progress_msg.edit(content=f"🔄 Limpeza: {deleted}/{limit}")
                await asyncio.sleep(normal_random((MIN_DELAY+MAX_DELAY)/2, 5, min_val=MIN_DELAY, max_val=MAX_DELAY))
                if deleted >= limit:
                    break
            last_id = msgs[-1]['id']
        return deleted

    async def _perform_backup(self, user_id, token, chat_id, progress_msg):
        headers = build_headers({"Authorization": token})
        messages = []
        last_id = None
        while len(messages) < MAX_BACKUP:
            url = f"https://discord.com/api/v10/channels/{chat_id}/messages?limit=100"
            if last_id:
                url += f"&before={last_id}"
            resp = await request_with_rate_limit('GET', url, headers=headers)
            if resp.status_code != 200:
                break
            msgs = resp.json()
            if not msgs:
                break
            for m in msgs:
                messages.append(f"[{m['timestamp']}] {m['author']['username']}: {m.get('content', '')}")
            last_id = msgs[-1]['id']
            await progress_msg.edit(content=f"📁 Backup: {len(messages)} mensagens capturadas")
            await asyncio.sleep(normal_random(2, 0.5, min_val=1))
        if not messages:
            await progress_msg.edit(content="❌ Nenhuma mensagem encontrada.")
            return None
        messages.reverse()
        content = "\n".join(messages)
        buffer = io.BytesIO(content.encode('utf-8'))
        return buffer

    async def _perform_farm(self, user_id, token, chat_id, message, interval, stop_event):
        try:
            while not stop_event.is_set():
                headers = build_headers({"Authorization": token})
                payload = {'content': message, 'nonce': str(generate_snowflake())}
                await request_with_rate_limit('POST', f'https://discord.com/api/v10/channels/{chat_id}/messages',
                                              headers=headers, json_data=payload)
                logger.info(f"Farm enviado para {user_id}: {message[:20]}...")
                delay = normal_random(interval, interval * 0.15, min_val=15)
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            logger.info(f"Farm cancelado para {user_id}")
            raise

    async def _perform_call(self, user_id, token, channel_id, hours, progress_msg):
        headers = build_headers({"Authorization": token})
        async with aiohttp.ClientSession() as aio_session:
            try:
                async with aio_session.get("https://discord.com/api/v10/gateway") as resp_gw:
                    if resp_gw.status != 200:
                        raise Exception("Gateway API failed")
                    gw_data = await resp_gw.json()
                    gateway_url = gw_data['url'] + "?v=10&encoding=json"
            except Exception:
                gateway_url = "wss://gateway.discord.gg/?v=10&encoding=json"

            resp = await request_with_rate_limit('GET', f'https://discord.com/api/v10/channels/{channel_id}', headers=headers)
            if resp.status_code != 200:
                await progress_msg.edit(content=f"❌ Erro ao acessar canal (status {resp.status_code})")
                return
            channel_data = resp.json()
            guild_id = channel_data.get('guild_id')
            if not guild_id:
                await progress_msg.edit(content="❌ Canal não pertence a um servidor de voz.")
                return

            voice_ws = await aio_session.ws_connect(gateway_url)
            try:
                hello = await voice_ws.receive_json()
                await voice_ws.send_json({
                    "op": 2,
                    "d": {
                        "token": token,
                        "properties": fingerprint_mgr.get(vary=False)
                    }
                })
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

                await progress_msg.edit(content=f"✅ Na call por {hours}h")
                end_time = time.time() + (hours * 3600)
                while time.time() < end_time:
                    try:
                        msg = await asyncio.wait_for(voice_ws.receive(), timeout=60.0)
                        if msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                            break
                    except asyncio.TimeoutError:
                        try:
                            await voice_ws.send_json({"op": 1, "d": None})
                        except:
                            break
                    except:
                        break
                    await asyncio.sleep(1)
                voice.stop()
                await voice_ws.close()
                await progress_msg.edit(content="⏹️ Call encerrada.")
            except asyncio.CancelledError:
                voice.stop()
                await voice_ws.close()
                await progress_msg.edit(content="⏹️ Call interrompida.")
                raise
            except Exception as e:
                logger.error(f"Erro na call: {e}")
                await progress_msg.edit(content=f"❌ Erro: {str(e)[:100]}")
                await voice_ws.close()

    async def _perform_clone(self, user_id, token, target_id, progress_msg):
        headers = build_headers({"Authorization": token})
        resp = await request_with_rate_limit('GET', f'https://discord.com/api/v10/users/{target_id}', headers=headers)
        if resp.status_code != 200:
            await progress_msg.edit(content="❌ Usuário não encontrado.")
            return
        target = resp.json()
        payload = {}
        if target.get('bio'):
            payload['bio'] = target['bio']
        if target.get('avatar'):
            av_url = f"https://cdn.discordapp.com/avatars/{target_id}/{target['avatar']}.png?size=1024"
            av_resp = await request_with_rate_limit('GET', av_url, headers=headers)
            if av_resp.status_code == 200:
                av_b64 = base64.b64encode(av_resp.content).decode()
                payload['avatar'] = f"data:image/png;base64,{av_b64}"
        if not payload:
            await progress_msg.edit(content="⚠️ Alvo sem bio ou avatar.")
            return
        patch_resp = await request_with_rate_limit('PATCH', 'https://discord.com/api/v10/users/@me',
                                                   headers=headers, json_data=payload)
        if patch_resp.status_code == 200:
            await progress_msg.edit(content="✅ Perfil clonado!")
        else:
            await progress_msg.edit(content=f"❌ Erro: {patch_resp.status_code}")

# ============================================================
# VIEW (BOTÕES E MODAIS)
# ============================================================
class DashboardView(discord.ui.View):
    def __init__(self, user, cog):
        super().__init__(timeout=300)
        self.user = user
        self.cog = cog
        self.add_item(ButtonAddToken(user))
        self.add_item(ButtonSetChannel(user))
        self.add_item(ButtonClean(user, cog))
        self.add_item(ButtonBackup(user, cog))
        self.add_item(ButtonFarm(user, cog))
        self.add_item(ButtonCall(user, cog))
        self.add_item(ButtonClone(user, cog))
        self.add_item(ButtonStatus(user))
        self.add_item(ButtonStopFarm(user, cog))
        self.add_item(ButtonStopCall(user, cog))

    async def interaction_check(self, interaction):
        return interaction.user.id == self.user.user_id

# ---------- BOTÃO: ADICIONAR TOKEN ----------
class ButtonAddToken(discord.ui.Button):
    def __init__(self, user):
        super().__init__(label="🔑 Adicionar Token", style=discord.ButtonStyle.success)
        self.user = user

    async def callback(self, interaction: discord.Interaction):
        modal = TokenModal(self.user)
        await interaction.response.send_modal(modal)

class TokenModal(discord.ui.Modal, title="🔑 Adicionar Token"):
    token_input = discord.ui.TextInput(label="Token do Discord", style=discord.TextStyle.paragraph, required=True)

    def __init__(self, user):
        super().__init__()
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        token = self.token_input.value.strip()
        if not token:
            await interaction.response.send_message("❌ Token vazio.", ephemeral=True)
            return
        tokens = self.user.data.get('tokens', [])
        tokens.append(token)
        self.user.data['tokens'] = tokens
        self.user.save()
        await interaction.response.send_message("✅ Token adicionado!", ephemeral=True)

# ---------- BOTÃO: DEFINIR CANAL ----------
class ButtonSetChannel(discord.ui.Button):
    def __init__(self, user):
        super().__init__(label="💬 Definir Canal", style=discord.ButtonStyle.primary)
        self.user = user

    async def callback(self, interaction: discord.Interaction):
        modal = ChannelModal(self.user)
        await interaction.response.send_modal(modal)

class ChannelModal(discord.ui.Modal, title="💬 Definir Canal"):
    channel_input = discord.ui.TextInput(label="ID do Canal de Texto", style=discord.TextStyle.short, required=True)
    tipo = discord.ui.TextInput(label="Tipo (clean/farm)", style=discord.TextStyle.short, default="clean", required=False)

    def __init__(self, user):
        super().__init__()
        self.user = user

    async def on_submit(self, interaction: discord.Interaction):
        try:
            chat_id = int(self.channel_input.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ ID inválido.", ephemeral=True)
            return
        tipo = self.tipo.value.strip().lower()
        if tipo == "farm":
            self.user.data['farm_chat_id'] = chat_id
        else:
            self.user.data['chat_id'] = chat_id
        self.user.save()
        await interaction.response.send_message(f"✅ Canal definido ({tipo}): <#{chat_id}>", ephemeral=True)

# ---------- BOTÃO: LIMPEZA ----------
class ButtonClean(discord.ui.Button):
    def __init__(self, user, cog):
        super().__init__(label="🧹 Limpeza", style=discord.ButtonStyle.danger)
        self.user = user
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        token = self.user.get_token()
        if not token:
            await interaction.response.send_message("❌ Nenhum token configurado.", ephemeral=True)
            return
        chat_id = self.user.data.get('chat_id')
        if not chat_id:
            await interaction.response.send_message("❌ Canal não definido.", ephemeral=True)
            return
        await interaction.response.defer()
        cancel_event = asyncio.Event()
        task_id = f"clean_{interaction.user.id}"
        self.cog.active_tasks[task_id] = cancel_event
        msg = await interaction.followup.send("🔄 Iniciando limpeza...")
        try:
            deleted = await self.cog._perform_cleanup(interaction.user.id, token, chat_id, MAX_MESSAGES, msg, cancel_event)
            await msg.edit(content=f"✅ Limpeza concluída: {deleted} mensagens deletadas.")
        except asyncio.CancelledError:
            await msg.edit(content="⏹️ Limpeza interrompida.")
        finally:
            self.cog.active_tasks.pop(task_id, None)

# ---------- BOTÃO: BACKUP ----------
class ButtonBackup(discord.ui.Button):
    def __init__(self, user, cog):
        super().__init__(label="💾 Backup", style=discord.ButtonStyle.primary)
        self.user = user
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        token = self.user.get_token()
        if not token:
            await interaction.response.send_message("❌ Nenhum token configurado.", ephemeral=True)
            return
        chat_id = self.user.data.get('chat_id')
        if not chat_id:
            await interaction.response.send_message("❌ Canal não definido.", ephemeral=True)
            return
        await interaction.response.defer()
        msg = await interaction.followup.send("📁 Iniciando backup...")
        buffer = await self.cog._perform_backup(interaction.user.id, token, chat_id, msg)
        if buffer:
            await msg.edit(content="✅ Backup concluído!")
            await interaction.followup.send(file=discord.File(buffer, filename="backup.txt"))
        else:
            await msg.edit(content="❌ Nenhuma mensagem encontrada.")

# ---------- BOTÃO: FARM ----------
class ButtonFarm(discord.ui.Button):
    def __init__(self, user, cog):
        super().__init__(label="⏰ Farm", style=discord.ButtonStyle.success)
        self.user = user
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        token = self.user.get_token()
        if not token:
            await interaction.response.send_message("❌ Nenhum token configurado.", ephemeral=True)
            return
        chat_id = self.user.data.get('farm_chat_id') or self.user.data.get('chat_id')
        if not chat_id:
            await interaction.response.send_message("❌ Canal de farm não definido.", ephemeral=True)
            return
        modal = FarmModal(self.user, self.cog, token, chat_id)
        await interaction.response.send_modal(modal)

class FarmModal(discord.ui.Modal, title="⏰ Configurar Farm"):
    message_input = discord.ui.TextInput(label="Mensagem", style=discord.TextStyle.paragraph, required=True)
    interval_input = discord.ui.TextInput(label="Intervalo (minutos)", style=discord.TextStyle.short, default="120", required=True)

    def __init__(self, user, cog, token, chat_id):
        super().__init__()
        self.user = user
        self.cog = cog
        self.token = token
        self.chat_id = chat_id

    async def on_submit(self, interaction: discord.Interaction):
        msg = self.message_input.value.strip()
        try:
            interval_min = float(self.interval_input.value.replace(',', '.'))
        except ValueError:
            await interaction.response.send_message("❌ Intervalo inválido.", ephemeral=True)
            return
        if interval_min < 15:
            await interaction.response.send_message("❌ Mínimo 15 minutos.", ephemeral=True)
            return
        interval_sec = interval_min * 60
        self.user.data['farm_message'] = msg
        self.user.data['farm_interval'] = interval_sec
        self.user.data['auto_farming'] = 1
        self.user.save()
        stop_event = asyncio.Event()
        task_id = f"farm_{interaction.user.id}"
        self.cog.active_tasks[task_id] = stop_event
        asyncio.create_task(self.cog._perform_farm(interaction.user.id, self.token, self.chat_id, msg, interval_sec, stop_event))
        await interaction.response.send_message(f"✅ Farm iniciado (a cada {interval_min} min).", ephemeral=True)

# ---------- BOTÃO: CALL ----------
class ButtonCall(discord.ui.Button):
    def __init__(self, user, cog):
        super().__init__(label="🎧 Call", style=discord.ButtonStyle.primary)
        self.user = user
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        token = self.user.get_token()
        if not token:
            await interaction.response.send_message("❌ Nenhum token configurado.", ephemeral=True)
            return
        modal = CallModal(self.user, self.cog, token)
        await interaction.response.send_modal(modal)

class CallModal(discord.ui.Modal, title="🎧 Entrar na Call"):
    channel_input = discord.ui.TextInput(label="ID do Canal de Voz", style=discord.TextStyle.short, required=True)
    hours_input = discord.ui.TextInput(label="Horas", style=discord.TextStyle.short, default="2", required=True)

    def __init__(self, user, cog, token):
        super().__init__()
        self.user = user
        self.cog = cog
        self.token = token

    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel_id = int(self.channel_input.value.strip())
            hours = float(self.hours_input.value.replace(',', '.'))
        except ValueError:
            await interaction.response.send_message("❌ Valores inválidos.", ephemeral=True)
            return
        if hours <= 0 or hours > 24:
            await interaction.response.send_message("❌ Horas entre 0.1 e 24.", ephemeral=True)
            return
        await interaction.response.defer()
        msg = await interaction.followup.send(f"🔄 Conectando por {hours}h...")
        task_id = f"call_{interaction.user.id}"
        cancel_event = asyncio.Event()
        self.cog.active_tasks[task_id] = cancel_event
        try:
            await self.cog._perform_call(interaction.user.id, self.token, channel_id, hours, msg)
        except asyncio.CancelledError:
            await msg.edit(content="⏹️ Call interrompida.")
        finally:
            self.cog.active_tasks.pop(task_id, None)

# ---------- BOTÃO: CLONAR PERFIL ----------
class ButtonClone(discord.ui.Button):
    def __init__(self, user, cog):
        super().__init__(label="🎭 Clonar Perfil", style=discord.ButtonStyle.secondary)
        self.user = user
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        token = self.user.get_token()
        if not token:
            await interaction.response.send_message("❌ Nenhum token configurado.", ephemeral=True)
            return
        modal = CloneModal(self.user, self.cog, token)
        await interaction.response.send_modal(modal)

class CloneModal(discord.ui.Modal, title="🎭 Clonar Perfil"):
    target_input = discord.ui.TextInput(label="ID do Usuário Alvo", style=discord.TextStyle.short, required=True)

    def __init__(self, user, cog, token):
        super().__init__()
        self.user = user
        self.cog = cog
        self.token = token

    async def on_submit(self, interaction: discord.Interaction):
        try:
            target_id = int(self.target_input.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ ID inválido.", ephemeral=True)
            return
        await interaction.response.defer()
        msg = await interaction.followup.send("🔄 Clonando perfil...")
        await self.cog._perform_clone(interaction.user.id, self.token, target_id, msg)

# ---------- BOTÃO: STATUS ----------
class ButtonStatus(discord.ui.Button):
    def __init__(self, user):
        super().__init__(label="📋 Status", style=discord.ButtonStyle.secondary)
        self.user = user

    async def callback(self, interaction: discord.Interaction):
        data = self.user.data
        tokens = data.get('tokens', [])
        embed = discord.Embed(title="📋 Status", color=discord.Color.green())
        embed.add_field(name="Tokens", value=f"{len(tokens)} configurados", inline=True)
        embed.add_field(name="Canal Limpeza", value=f"<#{data.get('chat_id')}>" if data.get('chat_id') else "Não definido", inline=True)
        embed.add_field(name="Canal Farm", value=f"<#{data.get('farm_chat_id')}>" if data.get('farm_chat_id') else "Não definido", inline=True)
        embed.add_field(name="Auto-Farm", value="✅ Ativo" if data.get('auto_farming') else "❌ Inativo", inline=True)
        embed.add_field(name="Mensagem Farm", value=data.get('farm_message', 'Nenhuma'), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ---------- BOTÕES: PARAR ----------
class ButtonStopFarm(discord.ui.Button):
    def __init__(self, user, cog):
        super().__init__(label="⏹️ Parar Farm", style=discord.ButtonStyle.danger)
        self.user = user
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        task_id = f"farm_{interaction.user.id}"
        if task_id in self.cog.active_tasks:
            self.cog.active_tasks[task_id].set()
            self.user.data['auto_farming'] = 0
            self.user.save()
            await interaction.response.send_message("⏹️ Farm interrompido.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nenhum farm ativo.", ephemeral=True)

class ButtonStopCall(discord.ui.Button):
    def __init__(self, user, cog):
        super().__init__(label="⏹️ Sair Call", style=discord.ButtonStyle.danger)
        self.user = user
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        task_id = f"call_{interaction.user.id}"
        if task_id in self.cog.active_tasks:
            self.cog.active_tasks[task_id].set()
            await interaction.response.send_message("⏹️ Saindo da call...", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nenhuma call ativa.", ephemeral=True)

# ============================================================
# SETUP
# ============================================================
async def setup(bot):
    await bot.add_cog(Panel(bot))
