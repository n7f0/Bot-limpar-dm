import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import os
import random
import time
import io
import base64
import json
import math
import socket
import struct
import secrets
from curl_cffi import requests as curl_requests
from curl_cffi.requests import AsyncSession
import aiohttp
from aiohttp import ClientWebSocketResponse, WSMsgType

# ============================================================
# CONFIGURAÇÃO DO BOT OFICIAL
# ============================================================
TOKEN_BOT = os.getenv('BOT_TOKEN')
if not TOKEN_BOT:
    print("❌ Defina a variável de ambiente BOT_TOKEN.")
    exit(1)

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

# ============================================================
# CONFIGURAÇÕES DE SEGURANÇA AVANÇADAS
# ============================================================
MIN_DELAY = 15.0
MAX_DELAY = 35.0
PAUSE_AFTER = 20
PAUSE_DUR_MIN = 120.0
PAUSE_DUR_MAX = 180.0
MAX_MESSAGES = 150
MAX_BACKUP = 3000

SLEEP_START_HOUR = 23
SLEEP_END_HOUR = 7

POST_TASK_REST_MIN = 5   # minutos
POST_TASK_REST_MAX = 15

# ============================================================
# FUNÇÕES ESTATÍSTICAS
# ============================================================
def normal_random(mean: float, std: float, min_val: float = 0, max_val: float = float('inf')) -> float:
    u1 = random.random()
    u2 = random.random()
    z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
    val = mean + std * z
    return max(min_val, min(val, max_val))

# ============================================================
# GERENCIADOR DE FINGERPRINT
# ============================================================
class FingerprintManager:
    CHROME_VERSIONS = ["120.0.6099.109", "121.0.6167.85", "122.0.6261.57", "123.0.6312.58"]
    OS_VERSIONS = ["10.0.22621", "10.0.19045", "10.0.22000", "10.0.20348"]
    BROWSER_VERSIONS = ["120.0.0.0", "121.0.0.0", "122.0.0.0", "123.0.0.0"]

    def __init__(self):
        self.device_id = secrets.token_hex(32)
        self.session_id = secrets.token_hex(32)
        self.base = self._generate()
        self.current = self.base.copy()
        self.last_rotate = time.time()

    def _generate(self):
        chrome = random.choice(self.CHROME_VERSIONS)
        os_ver = random.choice(self.OS_VERSIONS)
        browser = random.choice(self.BROWSER_VERSIONS)
        build = random.randint(230000, 250000)
        return {
            "os": "Windows",
            "browser": "Chrome",
            "device": "",
            "system_locale": "pt-BR",
            "browser_user_agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome} Safari/537.36",
            "browser_version": browser,
            "os_version": os_ver,
            "referrer": "",
            "referring_domain": "",
            "referrer_current": "",
            "referring_domain_current": "",
            "release_channel": "stable",
            "client_build_number": build,
            "client_event_source": None,
            "design_id": 0,
        }

    def get(self, vary: bool = True):
        if vary:
            fp = self.base.copy()
            fp['client_build_number'] = self.base['client_build_number'] + random.randint(-50, 50)
            ua = fp['browser_user_agent']
            if random.random() < 0.3:
                ua = ua.replace('Chrome/', f'Chrome/{random.choice(self.CHROME_VERSIONS)}')
            fp['browser_user_agent'] = ua
            return fp
        return self.current

    def rotate(self):
        self.base = self._generate()
        self.current = self.base.copy()
        self.session_id = secrets.token_hex(32)

    def get_context_headers(self):
        context = {
            "device_id": self.device_id,
            "session_id": self.session_id,
            "location": "Text Channel"
        }
        return {"X-Context-Properties": base64.b64encode(json.dumps(context).encode()).decode()}

fingerprint_mgr = FingerprintManager()

# ============================================================
# SESSÃO CURL_CFFI + HEADERS
# ============================================================
def build_headers(custom_headers: dict = None, vary_fingerprint: bool = True) -> dict:
    fp = fingerprint_mgr.get(vary=vary_fingerprint)
    headers = {
        "User-Agent": fp['browser_user_agent'],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "sec-ch-ua": f'"Chromium";v="{fp["browser_version"].split(".")[0]}", "Google Chrome";v="{fp["browser_version"].split(".")[0]}", "Not?A_Brand";v="8"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "Origin": "https://discord.com",
        "Referer": "https://discord.com/channels/@me",
        "DNT": "1",
        "X-Discord-Timezone": "America/Sao_Paulo",
        "X-Discord-Locale": "pt-BR",
        **fingerprint_mgr.get_context_headers()
    }
    if custom_headers:
        headers.update(custom_headers)
    return headers

session = AsyncSession(impersonate="chrome120")

# ============================================================
# WARMUP
# ============================================================
warmup_done = False

async def warmup(force=False):
    global warmup_done
    if warmup_done and not force:
        return
    try:
        headers = build_headers(vary_fingerprint=False)
        await session.get("https://discord.com", headers=headers)
        await session.get("https://discord.com/api/v9/experiments", headers=headers)
        await session.get("https://discord.com/api/v9/gateway", headers=headers)
        warmup_done = True
        print("✅ Warmup avançado concluído.")
    except Exception as e:
        print(f"⚠️ Erro no warmup: {e}")

# ============================================================
# ESTRUTURA DE DADOS GLOBAL
# ============================================================
user_data = {}

def get_user(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            'token': None, 'chat_id': None, 'cleaning': False,
            'clean_cancel': None, 'farming_call': False,
            'call_cancel': None, 'auto_farming': False, 'farm_cancel': None,
            'gateway_task': None, 'science_task': None,
            'gateway_ws': None, 'gateway_stop': False,
            'science_stop': False, 'sleep_mode': False,
            'last_activity': time.time(),
            'account_healthy': True,
            'resting_until': 0,
        }
    return user_data[user_id]

# ============================================================
# AUXILIARES
# ============================================================
EPOCH = 1420070400000
_increment = 0

def generate_snowflake() -> int:
    global _increment
    _increment = (_increment + 1) & 0xFFF
    now = int(time.time() * 1000) - EPOCH
    return (now << 22) | (0 << 17) | (0 << 12) | _increment

def is_sleep_time() -> bool:
    h = time.localtime().tm_hour
    if SLEEP_START_HOUR < SLEEP_END_HOUR:
        return SLEEP_START_HOUR <= h < SLEEP_END_HOUR
    else:
        return h >= SLEEP_START_HOUR or h < SLEEP_END_HOUR

async def check_sleep_mode(user_id: int) -> bool:
    data = get_user(user_id)
    if is_sleep_time():
        if not data.get('sleep_mode'):
            data['sleep_mode'] = True
            print(f"💤 Modo sono ativado para {user_id}")
        return True
    else:
        if data.get('sleep_mode'):
            data['sleep_mode'] = False
            print(f"☀️ Modo sono desativado para {user_id}")
        return False

async def check_account_health(user_id: int) -> bool:
    data = get_user(user_id)
    token = data.get('token')
    if not token:
        return False
    headers = build_headers({"Authorization": token})
    try:
        resp = await session.get("https://discord.com/api/v10/users/@me", headers=headers)
        print(f"🔍 Health check status: {resp.status_code}")  # Debug
        if resp.status_code == 200:
            data['account_healthy'] = True
            return True
        else:
            data['account_healthy'] = False
            print(f"⚠️ Health check falhou com status {resp.status_code}")
            return False
    except Exception as e:
        print(f"⚠️ Exceção no health check: {e}")
        data['account_healthy'] = False
        return False

async def post_task_rest(user_id: int):
    data = get_user(user_id)
    rest_duration = random.uniform(POST_TASK_REST_MIN * 60, POST_TASK_REST_MAX * 60)
    data['resting_until'] = time.time() + rest_duration
    print(f"😴 Pós-tarefa: descansando por {rest_duration/60:.1f} min.")
    await asyncio.sleep(rest_duration)
    data['resting_until'] = 0

async def check_resting(user_id: int) -> bool:
    data = get_user(user_id)
    return data['resting_until'] > time.time()

# ============================================================
# REQUEST COM RATE‑LIMIT (CORRIGIDA)
# ============================================================
async def request_with_rate_limit(method: str, url: str, headers: dict = None, json_data: dict = None, **kwargs):
    if not headers:
        headers = build_headers()
    resp = await session.request(method, url, headers=headers, json=json_data, **kwargs)

    # Agora usamos status_code
    if resp.status_code == 429:
        retry_after = float(resp.headers.get('Retry-After', 5))
        global_limit = resp.headers.get('X-RateLimit-Global')
        if global_limit and global_limit.lower() == 'true':
            await asyncio.sleep(retry_after + random.uniform(0.5, 2.0))
        else:
            await asyncio.sleep(retry_after + random.uniform(0.5, 1.5))
        return await request_with_rate_limit(method, url, headers, json_data, **kwargs)

    # Atualiza rate limit se houver
    remaining = resp.headers.get('X-RateLimit-Remaining')
    if remaining is not None and int(remaining) < 5:
        await asyncio.sleep(random.uniform(1.0, 3.0))

    return resp

# ============================================================
# SIMULAÇÕES (DIGITAÇÃO, ACK, REAÇÕES)
# ============================================================
async def simulate_typing(channel_id: int, token: str, duration: float = None):
    if duration is None:
        duration = random.uniform(1.5, 4.0)
    headers = build_headers({"Authorization": token, "Content-Type": "application/json"})
    url = f"https://discord.com/api/v10/channels/{channel_id}/typing"
    try:
        await request_with_rate_limit('POST', url, headers=headers)
        await asyncio.sleep(duration)
    except:
        pass

async def send_message_ack(channel_id: str, message_id: str, token: str, mention_count: int = 0):
    headers = build_headers({"Authorization": token, "Content-Type": "application/json"})
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}/ack"
    payload = {"token": None, "mention_count": mention_count}
    try:
        await request_with_rate_limit('POST', url, headers=headers, json_data=payload)
    except:
        pass

async def random_reaction(channel_id: str, message_id: str, token: str):
    emojis = ["👍", "❤️", "😂", "😮", "😢", "😡", "👀", "🔥", "✨"]
    emoji = random.choice(emojis)
    headers = build_headers({"Authorization": token})
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me"
    try:
        await request_with_rate_limit('PUT', url, headers=headers)
        await asyncio.sleep(random.uniform(1.0, 3.0))
    except:
        pass

# ============================================================
# GERENCIADOR DE VOZ (UDP/RTP)
# ============================================================
class VoiceConnection:
    def __init__(self, user_id, ws, token):
        self.user_id = user_id
        self.ws = ws
        self.token = token
        self.udp_socket = None
        self.ssrc = random.randint(100000, 999999)
        self.sequence = 0
        self.timestamp = 0
        self.is_running = False

    async def start(self):
        ready_msg = await self.ws.receive()
        data = json.loads(ready_msg.data)
        if data.get('op') == 2:  # READY
            ip = data['d']['ip']
            port = data['d']['port']
            self.ssrc = data['d']['ssrc']
            modes = data['d']['modes']
            mode = modes[0] if modes else 'xsalsa20_poly1305'

            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.settimeout(1.0)

            packet = bytearray(74)
            struct.pack_into('>I', packet, 0, self.ssrc)
            self.udp_socket.sendto(packet, (ip, port))

            resp, _ = self.udp_socket.recvfrom(74)
            external_ip = resp[8:].decode().split('\x00', 1)[0]
            external_port = struct.unpack('>H', resp[4:6])[0]

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

            self.is_running = True
            asyncio.create_task(self._udp_heartbeat())

    async def _udp_heartbeat(self):
        while self.is_running:
            if self.udp_socket:
                header = bytearray(12)
                header[0] = 0x80
                header[1] = 0x78
                struct.pack_into('>H', header, 2, self.sequence)
                struct.pack_into('>I', header, 4, self.timestamp)
                struct.pack_into('>I', header, 8, self.ssrc)
                self.sequence += 1
                self.timestamp += 960
                try:
                    self.udp_socket.sendto(header, (self.udp_socket.getpeername()[0], self.udp_socket.getpeername()[1]))
                except:
                    pass
            await asyncio.sleep(random.uniform(4.5, 6.0))

    def stop(self):
        self.is_running = False
        if self.udp_socket:
            self.udp_socket.close()

# ============================================================
# GATEWAY (PRESENÇA COM ALTERNÂNCIA AFK)
# ============================================================
async def gateway_presence(user_id: int):
    data = get_user(user_id)
    token = data['token']
    if not token:
        return

    fingerprint_mgr.rotate()
    super_props = fingerprint_mgr.get(vary=False)

    async with aiohttp.ClientSession() as aio_session:
        async with aio_session.get("https://discord.com/api/v10/gateway") as resp:
            if resp.status != 200:
                return
            gateway_url = (await resp.json())['url'] + "/?v=10&encoding=json"

        try:
            async with aio_session.ws_connect(gateway_url) as ws:
                data['gateway_ws'] = ws
                hello = await ws.receive_json()
                base_interval = hello['d']['heartbeat_interval'] / 1000.0

                await ws.send_json({
                    "op": 2,
                    "d": {
                        "token": token,
                        "properties": super_props,
                        "presence": {
                            "status": "online",
                            "since": 0,
                            "activities": [],
                            "afk": False
                        }
                    }
                })
                await ws.receive_json()

                last_status_change = time.time()
                status_cycle = random.uniform(1800, 7200)
                current_status = "online"
                afk_since = None

                while not data.get('gateway_stop', False):
                    mean_interval = base_interval + 0.1
                    adjusted_interval = normal_random(mean_interval, 0.05 * mean_interval, min_val=10.0)
                    if data.get('sleep_mode', False):
                        adjusted_interval *= 2.0
                    await asyncio.sleep(adjusted_interval)
                    if not data.get('gateway_stop', False):
                        await ws.send_json({"op": 1, "d": None})

                    if time.time() - last_status_change > status_cycle:
                        if current_status == "online":
                            current_status = "idle"
                            afk_since = int(time.time() * 1000)
                        else:
                            current_status = "online"
                            afk_since = None
                        last_status_change = time.time()
                        status_cycle = random.uniform(1800, 7200)
                        try:
                            await ws.send_json({
                                "op": 3,
                                "d": {
                                    "status": current_status,
                                    "since": afk_since,
                                    "activities": [],
                                    "afk": (current_status == "idle")
                                }
                            })
                        except:
                            pass
        except Exception as e:
            print(f"Gateway error: {e}")
        finally:
            data['gateway_ws'] = None
            data['gateway_task'] = None

def start_gateway(user_id: int):
    data = get_user(user_id)
    if data['gateway_task'] is None or data['gateway_task'].done():
        data['gateway_stop'] = False
        data['gateway_task'] = asyncio.create_task(gateway_presence(user_id))

def stop_gateway(user_id: int):
    data = get_user(user_id)
    data['gateway_stop'] = True
    if data['gateway_ws']:
        asyncio.create_task(data['gateway_ws'].close())
    if data['gateway_task'] and not data['gateway_task'].done():
        data['gateway_task'].cancel()

# ============================================================
# TELEMETRIA (SCIENCE) + MOUSE JITTER
# ============================================================
async def science_telemetry(user_id: int):
    data = get_user(user_id)
    token = data['token']
    if not token:
        return

    fake_guilds = [str(random.randint(100000000000000000, 999999999999999999)) for _ in range(5)]
    fake_channels = [str(random.randint(100000000000000000, 999999999999999999)) for _ in range(5)]

    while not data.get('science_stop', False):
        if await check_sleep_mode(user_id):
            await asyncio.sleep(300)
            continue

        guild_id = random.choice(fake_guilds)
        channel_id = random.choice(fake_channels)

        event_type = random.choice(["client_activity", "mouse_move", "channel_switch", "guild_switch", "message_read", "read_state"])
        if event_type in ("mouse_move", "client_activity"):
            x = random.randint(0, 1920)
            y = random.randint(0, 1080)
            payload = {
                "events": [{
                    "type": event_type,
                    "properties": {"x": x, "y": y, "guild_id": guild_id, "channel_id": channel_id,
                                   "location": "text_channel", "time": int(time.time() * 1000)}
                }]
            }
        else:
            payload = {
                "events": [{
                    "type": event_type,
                    "properties": {"guild_id": guild_id, "channel_id": channel_id,
                                   "location": "text_channel", "time": int(time.time() * 1000)}
                }]
            }

        headers = build_headers({"Authorization": token, "Content-Type": "application/json"})
        endpoint = random.choice(["/api/v10/science", "/api/v10/track", "/api/v10/events"])
        try:
            await request_with_rate_limit('POST', f"https://discord.com{endpoint}", headers=headers, json_data=payload)
        except:
            pass

        delay = normal_random(60, 20, min_val=10, max_val=180)
        await asyncio.sleep(delay)

def start_science(user_id: int):
    data = get_user(user_id)
    if data['science_task'] is None or data['science_task'].done():
        data['science_stop'] = False
        data['science_task'] = asyncio.create_task(science_telemetry(user_id))

def stop_science(user_id: int):
    data = get_user(user_id)
    data['science_stop'] = True
    if data['science_task'] and not data['science_task'].done():
        data['science_task'].cancel()

# ============================================================
# TAREFAS CORE (LIMPEZA, BACKUP, FARM, CLONE, VOZ)
# ============================================================
async def perform_schedule(token, chat_id, message, delay_sec):
    await asyncio.sleep(delay_sec)
    headers = build_headers({"Authorization": token, "Content-Type": "application/json"})
    await simulate_typing(chat_id, token, duration=random.uniform(1.0, 3.0))
    payload = {'content': message, 'nonce': str(generate_snowflake())}
    await request_with_rate_limit('POST', f'https://discord.com/api/v10/channels/{chat_id}/messages',
                                  headers=headers, json_data=payload)

async def perform_auto_farm(user_id, message, interval_sec):
    data = get_user(user_id)
    while data['auto_farming'] and not data['farm_cancel'].is_set():
        if await check_sleep_mode(user_id):
            while await check_sleep_mode(user_id):
                await asyncio.sleep(60)
            continue
        if await check_resting(user_id):
            await asyncio.sleep(30)
            continue

        headers = build_headers({"Authorization": data['token'], "Content-Type": "application/json"})
        await simulate_typing(data['chat_id'], data['token'], duration=random.uniform(1.0, 4.0))
        payload = {'content': message, 'nonce': str(generate_snowflake())}
        try:
            await request_with_rate_limit('POST', f'https://discord.com/api/v10/channels/{data["chat_id"]}/messages',
                                          headers=headers, json_data=payload)
        except:
            pass

        mean_interval = interval_sec
        std = 0.1 * mean_interval
        real_interval = normal_random(mean_interval, std, min_val=15)
        await asyncio.sleep(real_interval)

async def perform_backup(interaction: discord.Interaction, token, chat_id):
    headers = build_headers({"Authorization": token})
    last_id = None
    messages_str = []
    msg_ids = []

    await interaction.response.defer(ephemeral=False)
    prog_msg = await interaction.followup.send(f'🔄 **Backup Stealth Iniciado.** Limite: {MAX_BACKUP} msgs.')

    start_gateway(interaction.user.id)
    start_science(interaction.user.id)

    await asyncio.sleep(random.uniform(2.0, 5.0))

    page_count = 0
    while len(messages_str) < MAX_BACKUP:
        if await check_sleep_mode(interaction.user.id):
            await prog_msg.edit(content='💤 **Modo sono – backup pausado.**')
            while await check_sleep_mode(interaction.user.id):
                await asyncio.sleep(60)
            await prog_msg.edit(content='🔄 **Retomando backup...**')
            continue

        url = f'https://discord.com/api/v10/channels/{chat_id}/messages?limit=100'
        if last_id:
            url += f'&before={last_id}'

        resp = await request_with_rate_limit('GET', url, headers=headers)
        if resp.status_code != 200:
            break
        msgs = resp.json()
        if not msgs:
            break

        for m in msgs:
            author = m['author']['username']
            content = m.get('content', '[Vazio ou Anexo]')
            timestamp = m['timestamp']
            messages_str.append(f"[{timestamp}] {author}: {content}")
            msg_ids.append(m['id'])

        last_id = msgs[-1]['id']
        page_count += 1

        if msg_ids and random.random() < 0.3:
            ack_msg = random.choice(msg_ids)
            await send_message_ack(chat_id, ack_msg, token, mention_count=0)

        if msg_ids and random.random() < 0.2:
            react_msg = random.choice(msg_ids)
            await random_reaction(chat_id, react_msg, token)

        read_time = normal_random(5.0, 1.5, min_val=2.0, max_val=10.0)
        await asyncio.sleep(read_time)

        if page_count % 5 == 0:
            await prog_msg.edit(content=f'🔄 **Lendo...** {len(messages_str)} mensagens capturadas.')

    if not messages_str:
        await prog_msg.edit(content='❌ Nenhuma mensagem encontrada ou sem acesso.')
    else:
        messages_str.reverse()
        file_content = "\n".join(messages_str)
        buffer = io.BytesIO(file_content.encode('utf-8'))
        await prog_msg.edit(content=f'✅ **Backup concluído!** {len(messages_str)} mensagens.')
        await interaction.followup.send(file=discord.File(buffer, filename=f"backup_chat_{chat_id}.txt"))

    stop_gateway(interaction.user.id)
    stop_science(interaction.user.id)
    await post_task_rest(interaction.user.id)

async def perform_clone(user_id, target_id, progress_msg):
    data = get_user(user_id)
    headers = build_headers({"Authorization": data['token']})

    resp = await request_with_rate_limit('GET', f'https://discord.com/api/v10/users/{target_id}', headers=headers)
    if resp.status_code != 200:
        return await progress_msg.edit(content='❌ Usuário alvo não encontrado.')
    target_data = resp.json()

    payload = {}
    if 'bio' in target_data:
        payload['bio'] = target_data['bio']

    if target_data.get('avatar'):
        av_hash = target_data['avatar']
        av_url = f"https://cdn.discordapp.com/avatars/{target_id}/{av_hash}.png?size=1024"
        av_resp = await request_with_rate_limit('GET', av_url, headers=headers)
        if av_resp.status_code == 200:
            av_bytes = av_resp.content
            av_b64 = base64.b64encode(av_bytes).decode('utf-8')
            payload['avatar'] = f"data:image/png;base64,{av_b64}"

    await asyncio.sleep(random.uniform(2.0, 4.0))

    if payload:
        patch_resp = await request_with_rate_limit('PATCH', 'https://discord.com/api/v10/users/@me',
                                                   headers=headers, json_data=payload)
        if patch_resp.status_code == 200:
            await progress_msg.edit(content='✅ **Perfil clonado com sucesso!**')
        else:
            await progress_msg.edit(content=f'❌ Erro ao atualizar perfil: {patch_resp.status_code}')
    else:
        await progress_msg.edit(content='⚠️ O alvo não tem avatar ou bio configurada.')
    await post_task_rest(user_id)

async def perform_cleanup(interaction, token, chat_id, progress_msg):
    data = get_user(interaction.user.id)
    headers = build_headers({"Authorization": token, "Content-Type": "application/json"})
    messages_deleted, total_fetched = 0, 0
    last_id = None
    start_time = time.time()

    start_gateway(interaction.user.id)
    start_science(interaction.user.id)

    await asyncio.sleep(random.uniform(2.0, 6.0))

    while True:
        if data['clean_cancel'] and data['clean_cancel'].is_set():
            break
        if await check_sleep_mode(interaction.user.id):
            await progress_msg.edit(content='💤 **Modo sono – limpeza pausada.**')
            while await check_sleep_mode(interaction.user.id):
                await asyncio.sleep(60)
            await progress_msg.edit(content='🔄 **Retomando limpeza...**')
            continue
        if await check_resting(interaction.user.id):
            await asyncio.sleep(30)
            continue

        url = f'https://discord.com/api/v10/channels/{chat_id}/messages?limit=100'
        if last_id:
            url += f'&before={last_id}'

        resp = await request_with_rate_limit('GET', url, headers=headers)
        if resp.status_code != 200:
            break
        messages = resp.json()
        if not messages:
            break

        total_fetched += len(messages)

        for msg in messages:
            if data['clean_cancel'].is_set():
                break
            if msg['author']['id'] == str(interaction.user.id):
                del_url = f'https://discord.com/api/v10/channels/{chat_id}/messages/{msg["id"]}'
                del_resp = await request_with_rate_limit('DELETE', del_url, headers=headers)
                if del_resp.status_code == 204:
                    messages_deleted += 1
                    if messages_deleted % PAUSE_AFTER == 0:
                        pausa = random.uniform(PAUSE_DUR_MIN, PAUSE_DUR_MAX)
                        await progress_msg.edit(content=f'⏸️ **Pausa humana...** {int(pausa)}s.')
                        await asyncio.sleep(pausa)
                    elif messages_deleted % 3 == 0:
                        await progress_msg.edit(content=f'🔄 **Limpeza:** {messages_deleted}/{MAX_MESSAGES}')

                delay = normal_random((MIN_DELAY + MAX_DELAY) / 2, 5, min_val=MIN_DELAY, max_val=MAX_DELAY)
                await asyncio.sleep(delay)

            if messages_deleted >= MAX_MESSAGES:
                data['cleaning'] = False
                stop_gateway(interaction.user.id)
                stop_science(interaction.user.id)
                await progress_msg.edit(content=f'✅ **Limpeza concluída:** {messages_deleted} mensagens.')
                await post_task_rest(interaction.user.id)
                return

        last_id = messages[-1]['id']
        if len(messages) < 100:
            break

    data['cleaning'] = False
    stop_gateway(interaction.user.id)
    stop_science(interaction.user.id)
    await progress_msg.edit(content=f'✅ **Limpeza finalizada.** Deletadas: {messages_deleted}. Tempo: {int(time.time()-start_time)}s.')
    await post_task_rest(interaction.user.id)

async def perform_voice_farm(user_id, channel_id, hours, progress_msg):
    data = get_user(user_id)
    token = data['token']
    headers = build_headers({"Authorization": token})

    async with aiohttp.ClientSession() as aio_session:
        resp = await request_with_rate_limit('GET', f'https://discord.com/api/v10/channels/{channel_id}', headers=headers)
        if resp.status_code != 200:
            return await progress_msg.edit(content='❌ Erro ao acessar o canal.')
        channel_data = resp.json()
        guild_id = channel_data.get('guild_id')
        if not guild_id:
            return await progress_msg.edit(content='❌ O canal não pertence a um servidor (precisa ser canal de voz de servidor).')

        # WebSocket de voz
        voice_ws = await aio_session.ws_connect('wss://gateway.discord.gg/?v=10&encoding=json')
        hello = await voice_ws.receive_json()
        base_interval = hello['d']['heartbeat_interval'] / 1000.0

        await voice_ws.send_json({
            "op": 2,
            "d": {
                "token": token,
                "properties": fingerprint_mgr.get(vary=False)
            }
        })
        await voice_ws.receive_json()  # Ready

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
        await voice.start()

        await progress_msg.edit(content=f'✅ **Na call com RTP ativo por {hours}h**')

        end_time = time.time() + (hours * 3600)
        while time.time() < end_time and not data['call_cancel'].is_set():
            if await check_sleep_mode(user_id):
                break
            try:
                msg = await asyncio.wait_for(voice_ws.receive(), timeout=30)
                if msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    break
            except asyncio.TimeoutError:
                await voice_ws.send_json({"op": 1, "d": None})
            except:
                break

        voice.stop()
        await voice_ws.close()
        data['farming_call'] = False
        await progress_msg.edit(content='⏹️ **Call encerrada.**')
        await post_task_rest(user_id)

# ============================================================
# MODAIS (ENTRADA DE DADOS)
# ============================================================
class TokenModal(discord.ui.Modal, title='🔑 Configurar Token do Usuário'):
    token_input = discord.ui.TextInput(label='Token de usuário', style=discord.TextStyle.paragraph, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        get_user(interaction.user.id)['token'] = self.token_input.value.strip()
        await interaction.response.send_message('✅ Token configurado com sucesso!', ephemeral=True)
        await warmup()
        start_gateway(interaction.user.id)
        start_science(interaction.user.id)
        healthy = await check_account_health(interaction.user.id)
        if not healthy:
            await interaction.followup.send('⚠️ Token parece inválido ou conta restrita. Verifique se é um token de usuário (não de bot).', ephemeral=True)

class ChatModal(discord.ui.Modal, title='💬 Definir Chat (DM ou Servidor)'):
    chat_input = discord.ui.TextInput(label='ID do Canal/DM', style=discord.TextStyle.short, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            chat_id = int(self.chat_input.value.strip())
        except ValueError:
            return await interaction.response.send_message('❌ ID inválido. Apenas números.', ephemeral=True)

        data = get_user(interaction.user.id)
        if not data.get('token'):
            return await interaction.response.send_message('❌ Configure o token primeiro.', ephemeral=True)

        headers = build_headers({"Authorization": data['token']})
        resp = await request_with_rate_limit('GET', f'https://discord.com/api/v10/channels/{chat_id}', headers=headers)
        if resp.status_code != 200:
            return await interaction.response.send_message('❌ Canal não encontrado ou sem permissão.', ephemeral=True)

        data['chat_id'] = chat_id
        await interaction.response.send_message(f'✅ Chat alvo definido: `{chat_id}`', ephemeral=True)

class ScheduleModal(discord.ui.Modal, title='⏰ Agendar Mensagem'):
    msg_input = discord.ui.TextInput(label='Mensagem a ser enviada', style=discord.TextStyle.paragraph, required=True)
    delay_input = discord.ui.TextInput(label='Daqui a quantos minutos?', style=discord.TextStyle.short, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            delay_min = float(self.delay_input.value.strip().replace(',', '.'))
        except ValueError:
            return await interaction.response.send_message('❌ Tempo inválido.', ephemeral=True)
        if delay_min < 1:
            return await interaction.response.send_message('❌ O tempo mínimo é de 1 minuto.', ephemeral=True)

        data = get_user(interaction.user.id)
        bot.loop.create_task(perform_schedule(data['token'], data['chat_id'], self.msg_input.value, delay_min * 60))
        await interaction.response.send_message(f'✅ Mensagem agendada para daqui a {delay_min} minutos.', ephemeral=True)

class FarmBumperModal(discord.ui.Modal, title='🔄 Auto-Farm (Seguro)'):
    cmd_input = discord.ui.TextInput(label='Comando/Mensagem (Ex: !bump)', style=discord.TextStyle.short, required=True)
    interval_input = discord.ui.TextInput(label='Minutos (Mín: 15)', style=discord.TextStyle.short, default='120', required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            interval_min = float(self.interval_input.value.strip().replace(',', '.'))
        except ValueError:
            return await interaction.response.send_message('❌ Intervalo inválido.', ephemeral=True)
        if interval_min < 15:
            return await interaction.response.send_message('🛡️ **Anti-Ban:** Para sua segurança, o intervalo mínimo permitido é de 15 minutos.', ephemeral=True)

        data = get_user(interaction.user.id)
        data['auto_farming'] = True
        data['farm_cancel'] = asyncio.Event()

        await interaction.response.send_message(f'✅ Auto-Farm furtivo iniciado. Envio a cada {interval_min} min.', ephemeral=True)
        bot.loop.create_task(perform_auto_farm(interaction.user.id, self.cmd_input.value, interval_min * 60))

class CloneModal(discord.ui.Modal, title='🎭 Clonar Perfil'):
    target_input = discord.ui.TextInput(label='ID do Usuário Alvo', style=discord.TextStyle.short, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            target_id = int(self.target_input.value.strip())
        except ValueError:
            return await interaction.response.send_message('❌ ID inválido.', ephemeral=True)

        await interaction.response.defer(ephemeral=False)
        msg = await interaction.followup.send('🔄 **Lendo dados do perfil com segurança...**')
        bot.loop.create_task(perform_clone(interaction.user.id, target_id, msg))

class CallModal(discord.ui.Modal, title='🎧 Entrar em Call'):
    channel_input = discord.ui.TextInput(label='ID do Canal de Voz', style=discord.TextStyle.short, required=True)
    hours_input = discord.ui.TextInput(label='Tempo (Horas)', style=discord.TextStyle.short, default='2', required=True)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel_id = int(self.channel_input.value)
            hours = float(self.hours_input.value.replace(',', '.'))
        except:
            return await interaction.response.send_message('❌ Valores inválidos.', ephemeral=True)

        data = get_user(interaction.user.id)
        data['farming_call'] = True
        data['call_cancel'] = asyncio.Event()

        await interaction.response.defer()
        msg = await interaction.followup.send(f'🔄 **Negociando conexão com o Gateway...**')
        bot.loop.create_task(perform_voice_farm(interaction.user.id, channel_id, hours, msg))

# ============================================================
# PAINEL PRINCIPAL (VIEW)
# ============================================================
class PainelPrincipal(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    async def check(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('❌ Acesso restrito.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='🔑 Token', style=discord.ButtonStyle.primary, row=0)
    async def btn_token(self, i: discord.Interaction, b: discord.ui.Button):
        if await self.check(i):
            await i.response.send_modal(TokenModal())

    @discord.ui.button(label='💬 Set Chat', style=discord.ButtonStyle.success, row=0)
    async def btn_chat(self, i: discord.Interaction, b: discord.ui.Button):
        if await self.check(i):
            await i.response.send_modal(ChatModal())

    @discord.ui.button(label='💾 Backup', style=discord.ButtonStyle.secondary, row=0)
    async def btn_backup(self, i: discord.Interaction, b: discord.ui.Button):
        if not await self.check(i):
            return
        data = get_user(self.user_id)
        if not data['token'] or not data['chat_id']:
            return await i.response.send_message('❌ Defina Token e Chat.', ephemeral=True)
        if not await check_account_health(self.user_id):
            return await i.response.send_message('❌ Conta com problemas. Verifique o token.', ephemeral=True)
        bot.loop.create_task(perform_backup(i, data['token'], data['chat_id']))

    @discord.ui.button(label='🧹 Limpar', style=discord.ButtonStyle.danger, row=1)
    async def btn_clean(self, i: discord.Interaction, b: discord.ui.Button):
        if not await self.check(i):
            return
        data = get_user(self.user_id)
        if not data['token'] or not data['chat_id']:
            return await i.response.send_message('❌ Defina Token e Chat.', ephemeral=True)
        if data['cleaning']:
            return await i.response.send_message('⏳ Já em execução.', ephemeral=True)
        if not await check_account_health(self.user_id):
            return await i.response.send_message('❌ Conta com problemas.', ephemeral=True)
        data['cleaning'] = True
        data['clean_cancel'] = asyncio.Event()
        await i.response.defer()
        msg = await i.followup.send('🔄 **Iniciando limpeza...**')
        bot.loop.create_task(perform_cleanup(i, data['token'], data['chat_id'], msg))

    @discord.ui.button(label='⏹️ Parar Limpeza', style=discord.ButtonStyle.secondary, row=1)
    async def btn_stop_clean(self, i: discord.Interaction, b: discord.ui.Button):
        if await self.check(i):
            data = get_user(self.user_id)
            if data['clean_cancel']:
                data['clean_cancel'].set()
            await i.response.send_message('⏹️ Abortando limpeza...', ephemeral=True)

    @discord.ui.button(label='⏰ Agendar', style=discord.ButtonStyle.primary, row=2)
    async def btn_schedule(self, i: discord.Interaction, b: discord.ui.Button):
        if not await self.check(i):
            return
        if not get_user(self.user_id)['chat_id']:
            return await i.response.send_message('❌ Defina Chat Alvo.', ephemeral=True)
        await i.response.send_modal(ScheduleModal())

    @discord.ui.button(label='🔄 Auto-Farm', style=discord.ButtonStyle.success, row=2)
    async def btn_farm(self, i: discord.Interaction, b: discord.ui.Button):
        if not await self.check(i):
            return
        if not get_user(self.user_id)['chat_id']:
            return await i.response.send_message('❌ Defina Chat Alvo.', ephemeral=True)
        if not await check_account_health(self.user_id):
            return await i.response.send_message('❌ Conta com problemas.', ephemeral=True)
        await i.response.send_modal(FarmBumperModal())

    @discord.ui.button(label='⏹️ Parar Farm', style=discord.ButtonStyle.secondary, row=2)
    async def btn_stop_farm(self, i: discord.Interaction, b: discord.ui.Button):
        if await self.check(i):
            data = get_user(self.user_id)
            data['auto_farming'] = False
            if data['farm_cancel']:
                data['farm_cancel'].set()
            await i.response.send_message('⏹️ Farm interrompido.', ephemeral=True)

    @discord.ui.button(label='🎭 Clonar', style=discord.ButtonStyle.primary, row=3)
    async def btn_clone(self, i: discord.Interaction, b: discord.ui.Button):
        if not await self.check(i):
            return
        if not get_user(self.user_id)['token']:
            return await i.response.send_message('❌ Defina o Token.', ephemeral=True)
        await i.response.send_modal(CloneModal())

    @discord.ui.button(label='🎧 Call', style=discord.ButtonStyle.success, row=3)
    async def btn_call(self, i: discord.Interaction, b: discord.ui.Button):
        if not await self.check(i):
            return
        if not get_user(self.user_id)['token']:
            return await i.response.send_message('❌ Defina o Token.', ephemeral=True)
        await i.response.send_modal(CallModal())

    @discord.ui.button(label='⏹️ Sair Call', style=discord.ButtonStyle.danger, row=3)
    async def btn_stop_call(self, i: discord.Interaction, b: discord.ui.Button):
        if await self.check(i):
            data = get_user(self.user_id)
            if data['call_cancel']:
                data['call_cancel'].set()
            await i.response.send_message('⏹️ Desconectando...', ephemeral=True)

# ============================================================
# COMANDO PRINCIPAL
# ============================================================
@bot.tree.command(name='paineldm', description='Abre a suíte avançada com segurança máxima.')
async def paineldm(interaction: discord.Interaction):
    await warmup()
    embed = discord.Embed(
        title='🛡️ Master Panel - Modo Furtivo Avançado',
        description='Fingerprint dinâmico, heartbeat adaptativo, simulação de UI, rate-limit global, modo sono, fadiga pós-tarefa, ACK, reações, voz RTP.',
        color=discord.Color.brand_green()
    )
    embed.add_field(name='🧹 Limpeza', value=f'Delay: {MIN_DELAY}-{MAX_DELAY}s\nCota: {MAX_MESSAGES} msgs/sessão.', inline=False)
    embed.add_field(name='💤 Modo Sono', value=f'{SLEEP_START_HOUR}:00 - {SLEEP_END_HOUR}:00', inline=False)
    embed.add_field(name='😴 Descanso Pós-Tarefa', value=f'{POST_TASK_REST_MIN}-{POST_TASK_REST_MAX} min', inline=False)
    await interaction.response.send_message(embed=embed, view=PainelPrincipal(interaction.user.id), ephemeral=False)

@bot.event
async def on_ready():
    print(f'✅ Bot Mestre [Modo Furtivo Avançado] operando como {bot.user}')
    await warmup()
    await bot.tree.sync()

if __name__ == "__main__":
    bot.run(TOKEN_BOT)