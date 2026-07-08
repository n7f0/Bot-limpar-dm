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
import sqlite3
import sys

# Tentar importar psycopg2, se falhar usar SQLite
try:
    import psycopg2
    from psycopg2 import sql, extras
    USE_POSTGRES = True
except ImportError:
    USE_POSTGRES = False
    print("⚠️ psycopg2 não instalado. Usando SQLite como fallback.")

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
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# ============================================================
# CONFIGURAÇÕES DE SEGURANÇA
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
POST_TASK_REST_MIN = 5
POST_TASK_REST_MAX = 15
HEALTH_CHECK_INTERVAL = 300

# ============================================================
# BANCO DE DADOS (POSTGRESQL OU SQLITE)
# ============================================================
DB_TYPE = None

def init_db():
    global DB_TYPE
    if USE_POSTGRES:
        try:
            conn = psycopg2.connect(
                host=os.getenv('POSTGRES_HOST', 'localhost'),
                port=os.getenv('POSTGRES_PORT', '5432'),
                user=os.getenv('POSTGRES_USER', 'postgres'),
                password=os.getenv('POSTGRES_PASSWORD', ''),
                database=os.getenv('POSTGRES_DATABASE', 'discord_bot')
            )
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_config (
                    user_id BIGINT PRIMARY KEY,
                    token TEXT,
                    chat_id BIGINT,
                    farm_chat_id BIGINT,
                    auto_farming BOOLEAN DEFAULT FALSE,
                    farm_interval INTEGER DEFAULT 120,
                    farm_message TEXT,
                    sleep_mode BOOLEAN DEFAULT FALSE,
                    last_health_check TIMESTAMP,
                    token_valid BOOLEAN DEFAULT TRUE
                )
            ''')
            conn.commit()
            cursor.close()
            conn.close()
            DB_TYPE = 'postgres'
            print("✅ Conectado ao PostgreSQL com sucesso.")
            return True
        except Exception as e:
            print(f"⚠️ Erro ao conectar ao PostgreSQL: {e}")
            print("⚠️ Usando SQLite como fallback.")

    # Fallback SQLite
    DB_TYPE = 'sqlite'
    conn = sqlite3.connect('config.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_config (
            user_id INTEGER PRIMARY KEY,
            token TEXT,
            chat_id INTEGER,
            farm_chat_id INTEGER,
            auto_farming INTEGER DEFAULT 0,
            farm_interval INTEGER DEFAULT 120,
            farm_message TEXT,
            sleep_mode INTEGER DEFAULT 0,
            last_health_check TIMESTAMP,
            token_valid INTEGER DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ Usando SQLite (config.db)")
    return True

init_db()

def get_db_connection():
    if DB_TYPE == 'postgres':
        return psycopg2.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=os.getenv('POSTGRES_PORT', '5432'),
            user=os.getenv('POSTGRES_USER', 'postgres'),
            password=os.getenv('POSTGRES_PASSWORD', ''),
            database=os.getenv('POSTGRES_DATABASE', 'discord_bot')
        )
    else:
        return sqlite3.connect('config.db')

def load_user_config(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    if DB_TYPE == 'postgres':
        cursor.execute('SELECT token, chat_id, farm_chat_id, auto_farming, farm_interval, farm_message, sleep_mode, token_valid FROM user_config WHERE user_id = %s', (user_id,))
        row = cursor.fetchone()
    else:
        cursor.execute('SELECT token, chat_id, farm_chat_id, auto_farming, farm_interval, farm_message, sleep_mode, token_valid FROM user_config WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
    conn.close()
    if row:
        return {
            'token': row[0],
            'chat_id': row[1],
            'farm_chat_id': row[2],
            'auto_farming': bool(row[3]),
            'farm_interval': row[4],
            'farm_message': row[5],
            'sleep_mode': bool(row[6]),
            'token_valid': bool(row[7]) if len(row) > 7 else True
        }
    return None

def save_user_config(user_id, data):
    conn = get_db_connection()
    cursor = conn.cursor()
    if DB_TYPE == 'postgres':
        cursor.execute('''
            INSERT INTO user_config (user_id, token, chat_id, farm_chat_id, auto_farming, farm_interval, farm_message, sleep_mode, token_valid)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                token = EXCLUDED.token,
                chat_id = EXCLUDED.chat_id,
                farm_chat_id = EXCLUDED.farm_chat_id,
                auto_farming = EXCLUDED.auto_farming,
                farm_interval = EXCLUDED.farm_interval,
                farm_message = EXCLUDED.farm_message,
                sleep_mode = EXCLUDED.sleep_mode,
                token_valid = EXCLUDED.token_valid
        ''', (
            user_id,
            data.get('token'),
            data.get('chat_id'),
            data.get('farm_chat_id'),
            data.get('auto_farming', False),
            data.get('farm_interval', 120),
            data.get('farm_message', ''),
            data.get('sleep_mode', False),
            data.get('token_valid', True)
        ))
    else:
        cursor.execute('''
            INSERT OR REPLACE INTO user_config (user_id, token, chat_id, farm_chat_id, auto_farming, farm_interval, farm_message, sleep_mode, token_valid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            data.get('token'),
            data.get('chat_id'),
            data.get('farm_chat_id'),
            1 if data.get('auto_farming') else 0,
            data.get('farm_interval', 120),
            data.get('farm_message', ''),
            1 if data.get('sleep_mode') else 0,
            1 if data.get('token_valid') else 0
        ))
    conn.commit()
    conn.close()

def update_user_field(user_id, field, value):
    conn = get_db_connection()
    cursor = conn.cursor()
    if DB_TYPE == 'postgres':
        query = sql.SQL("UPDATE user_config SET {} = %s WHERE user_id = %s").format(sql.Identifier(field))
        cursor.execute(query, (value, user_id))
    else:
        cursor.execute(f"UPDATE user_config SET {field} = ? WHERE user_id = ?", (value, user_id))
    conn.commit()
    conn.close()

# ============================================================
# FUNÇÕES ESTATÍSTICAS
# ============================================================
def normal_random(mean: float, std: float, min_val: float = 0, max_val: float = float('inf')) -> float:
    u1 = random.random()
    u2 = random.random()
    z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
    val = mean + std * z
    return max(min_val, min(val, max_val))

def exponential_random(mean: float, min_val: float = 0, max_val: float = float('inf')) -> float:
    val = random.expovariate(1.0 / mean) if mean > 0 else 0
    return max(min_val, min(val, max_val))

# ============================================================
# GERENCIADOR DE FINGERPRINT (ROTAÇÃO AUTOMÁTICA)
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
        self.rotate_interval = random.uniform(1800, 7200)

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
        if time.time() - self.last_rotate > self.rotate_interval:
            self.rotate()
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
        self.device_id = secrets.token_hex(32)
        self.last_rotate = time.time()
        self.rotate_interval = random.uniform(1800, 7200)

    def get_context_headers(self):
        context = {
            "device_id": self.device_id,
            "session_id": self.session_id,
            "location": "Text Channel"
        }
        return {"X-Context-Properties": base64.b64encode(json.dumps(context).encode()).decode()}

fingerprint_mgr = FingerprintManager()

# ============================================================
# SESSÃO CURL_CFFI + HEADERS REALISTAS
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
# WARMUP AVANÇADO
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
        await session.get("https://discord.com/api/v9/applications/", headers=headers)
        await session.get("https://discord.com/api/v9/science", headers=headers)
        warmup_done = True
        print("✅ Warmup avançado concluído.")
    except Exception as e:
        print(f"⚠️ Erro no warmup: {e}")

# ============================================================
# ESTRUTURA DE DADOS EM MEMÓRIA
# ============================================================
user_data = {}

def get_user(user_id):
    if user_id not in user_data:
        config = load_user_config(user_id)
        if config:
            user_data[user_id] = {
                'token': config['token'],
                'chat_id': config['chat_id'],
                'farm_chat_id': config['farm_chat_id'],
                'cleaning': False,
                'clean_cancel': None,
                'farming_call': False,
                'call_cancel': None,
                'auto_farming': config['auto_farming'],
                'farm_cancel': None,
                'farm_interval': config['farm_interval'],
                'farm_message': config['farm_message'],
                'gateway_task': None,
                'science_task': None,
                'health_task': None,
                'gateway_ws': None,
                'gateway_stop': False,
                'science_stop': False,
                'sleep_mode': config['sleep_mode'],
                'token_valid': config.get('token_valid', True),
                'last_activity': time.time(),
                'account_healthy': True,
                'resting_until': 0,
                'rate_limits': {},
            }
        else:
            user_data[user_id] = {
                'token': None,
                'chat_id': None,
                'farm_chat_id': None,
                'cleaning': False,
                'clean_cancel': None,
                'farming_call': False,
                'call_cancel': None,
                'auto_farming': False,
                'farm_cancel': None,
                'farm_interval': 120,
                'farm_message': '',
                'gateway_task': None,
                'science_task': None,
                'health_task': None,
                'gateway_ws': None,
                'gateway_stop': False,
                'science_stop': False,
                'sleep_mode': False,
                'token_valid': True,
                'last_activity': time.time(),
                'account_healthy': True,
                'resting_until': 0,
                'rate_limits': {},
            }
    return user_data[user_id]

def save_user_to_db(user_id):
    data = get_user(user_id)
    save_user_config(user_id, {
        'token': data['token'],
        'chat_id': data['chat_id'],
        'farm_chat_id': data['farm_chat_id'],
        'auto_farming': data['auto_farming'],
        'farm_interval': data['farm_interval'],
        'farm_message': data['farm_message'],
        'sleep_mode': data['sleep_mode'],
        'token_valid': data.get('token_valid', True)
    })

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
            update_user_field(user_id, 'sleep_mode', True if DB_TYPE == 'postgres' else 1)
            print(f"💤 Modo sono ativado para {user_id}")
        return True
    else:
        if data.get('sleep_mode'):
            data['sleep_mode'] = False
            update_user_field(user_id, 'sleep_mode', False if DB_TYPE == 'postgres' else 0)
            print(f"☀️ Modo sono desativado para {user_id}")
        return False

async def check_account_health(user_id: int) -> bool:
    data = get_user(user_id)
    token = data.get('token')
    if not token:
        data['token_valid'] = False
        return False
    headers = build_headers({"Authorization": token})
    try:
        resp = await session.get("https://discord.com/api/v10/users/@me", headers=headers)
        if resp.status_code == 200:
            data['token_valid'] = True
            data['account_healthy'] = True
            update_user_field(user_id, 'token_valid', True if DB_TYPE == 'postgres' else 1)
            return True
        else:
            data['token_valid'] = False
            data['account_healthy'] = False
            update_user_field(user_id, 'token_valid', False if DB_TYPE == 'postgres' else 0)
            return False
    except Exception as e:
        data['token_valid'] = False
        data['account_healthy'] = False
        return False

async def periodic_health_check(user_id: int):
    while True:
        await asyncio.sleep(HEALTH_CHECK_INTERVAL)
        data = get_user(user_id)
        if data.get('gateway_stop', False):
            break
        await check_account_health(user_id)

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

async def simulate_navigation(user_id: int, token: str):
    if random.random() < 0.1:
        headers = build_headers({"Authorization": token})
        try:
            await session.get("https://discord.com/api/v9/users/@me/settings", headers=headers)
            await session.get("https://discord.com/api/v9/users/@me/connections", headers=headers)
            await asyncio.sleep(random.uniform(1.0, 3.0))
        except:
            pass

# ============================================================
# REQUEST COM RATE‑LIMIT ADAPTATIVO
# ============================================================
async def request_with_rate_limit(method: str, url: str, headers: dict = None, json_data: dict = None, **kwargs):
    if not headers:
        headers = build_headers()
    resp = await session.request(method, url, headers=headers, json=json_data, **kwargs)

    remaining = resp.headers.get('X-RateLimit-Remaining')
    reset_after = resp.headers.get('X-RateLimit-Reset-After')
    global_limit = resp.headers.get('X-RateLimit-Global')
    bucket = resp.headers.get('X-RateLimit-Bucket')

    if resp.status_code == 429:
        retry_after = float(resp.headers.get('Retry-After', 5))
        if global_limit and global_limit.lower() == 'true':
            wait = retry_after + random.uniform(0.5, 2.0) + exponential_random(5, 0, 10)
            await asyncio.sleep(wait)
        else:
            wait = retry_after + random.uniform(0.5, 1.5)
            await asyncio.sleep(wait)
        return await request_with_rate_limit(method, url, headers, json_data, **kwargs)

    if remaining is not None and int(remaining) < 5:
        wait = random.uniform(1.0, 5.0) + exponential_random(2, 0, 10)
        await asyncio.sleep(wait)

    return resp

# ============================================================
# SIMULAÇÕES (DIGITAÇÃO, ACK, REAÇÕES)
# ============================================================
async def simulate_typing(channel_id: int, token: str, duration: float = None):
    if duration is None:
        duration = normal_random(2.5, 0.8, min_val=0.8, max_val=6.0)
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
# GERENCIADOR DE VOZ (UDP/RTP) – CORRIGIDO
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
        self.udp_task = None

    async def start(self):
        try:
            ready_msg = await self.ws.receive()
            data = json.loads(ready_msg.data)
            if data.get('op') == 2:
                ip = data['d']['ip']
                port = data['d']['port']
                self.ssrc = data['d']['ssrc']
                modes = data['d']['modes']
                mode = modes[0] if modes else 'xsalsa20_poly1305'

                self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.udp_socket.settimeout(2.0)

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
                self.udp_task = asyncio.create_task(self._udp_heartbeat())
                print(f"✅ Voice UDP iniciado para {self.user_id} (SSRC: {self.ssrc})")
                return True
        except Exception as e:
            print(f"❌ Erro ao iniciar conexão de voz: {e}")
            return False

    async def _udp_heartbeat(self):
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
                self.udp_socket.sendto(header, (self.udp_socket.getpeername()[0], self.udp_socket.getpeername()[1]))
            except Exception as e:
                print(f"⚠️ Erro no UDP heartbeat: {e}")
            wait = random.uniform(4.0, 8.0)
            await asyncio.sleep(wait)

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
# GATEWAY (PRESENÇA COM ALTERNÂNCIA AFK)
# ============================================================
async def gateway_presence(user_id: int):
    data = get_user(user_id)
    token = data['token']
    if not token or not data.get('token_valid', True):
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
                    mean_interval = base_interval + random.uniform(0.05, 0.15)
                    std = 0.05 * mean_interval
                    adjusted_interval = normal_random(mean_interval, std, min_val=10.0)
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
            print(f"Gateway error for {user_id}: {e}")
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
# TELEMETRIA (SCIENCE)
# ============================================================
async def science_telemetry(user_id: int):
    data = get_user(user_id)
    token = data['token']
    if not token or not data.get('token_valid', True):
        return

    fake_guilds = [str(random.randint(100000000000000000, 999999999999999999)) for _ in range(10)]
    fake_channels = [str(random.randint(100000000000000000, 999999999999999999)) for _ in range(10)]

    while not data.get('science_stop', False):
        if await check_sleep_mode(user_id):
            await asyncio.sleep(300)
            continue

        guild_id = random.choice(fake_guilds)
        channel_id = random.choice(fake_channels)

        event_types = ["client_activity", "mouse_move", "channel_switch", "guild_switch", "message_read", "read_state"]
        weights = [0.3, 0.3, 0.1, 0.1, 0.1, 0.1]
        event_type = random.choices(event_types, weights=weights)[0]

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
# TAREFAS CORE
# ============================================================
async def perform_schedule(token, chat_id, message, delay_sec):
    await asyncio.sleep(delay_sec)
    headers = build_headers({"Authorization": token, "Content-Type": "application/json"})
    await simulate_typing(chat_id, token, duration=normal_random(2.0, 0.6, min_val=0.8, max_val=5.0))
    payload = {'content': message, 'nonce': str(generate_snowflake())}
    await request_with_rate_limit('POST', f'https://discord.com/api/v10/channels/{chat_id}/messages',
                                  headers=headers, json_data=payload)

async def perform_auto_farm(user_id, message, interval_sec):
    data = get_user(user_id)
    message_counter = 0
    while data['auto_farming'] and not data['farm_cancel'].is_set():
        if await check_sleep_mode(user_id):
            while await check_sleep_mode(user_id):
                await asyncio.sleep(60)
            continue
        if await check_resting(user_id):
            await asyncio.sleep(30)
            continue
        if not data.get('token_valid', True):
            await asyncio.sleep(60)
            continue

        chat_id = data.get('farm_chat_id') or data.get('chat_id')
        if not chat_id:
            await asyncio.sleep(60)
            continue

        if random.random() < 0.2:
            emojis = [" 👍", " ❤️", " 😂", " ✨", " 🔥", " 👀", ""]
            msg = message + random.choice(emojis)
        else:
            msg = message

        headers = build_headers({"Authorization": data['token'], "Content-Type": "application/json"})
        await simulate_typing(chat_id, data['token'], duration=normal_random(2.5, 0.8, min_val=1.0, max_val=5.0))
        payload = {'content': msg, 'nonce': str(generate_snowflake())}
        try:
            await request_with_rate_limit('POST', f'https://discord.com/api/v10/channels/{chat_id}/messages',
                                          headers=headers, json_data=payload)
            message_counter += 1
        except:
            pass

        if message_counter % 5 == 0:
            pausa = exponential_random(60, min_val=30, max_val=120)
            await asyncio.sleep(pausa)

        mean_interval = interval_sec
        std = 0.15 * mean_interval
        real_interval = normal_random(mean_interval, std, min_val=15)
        await asyncio.sleep(real_interval)

async def perform_backup(interaction: discord.Interaction, token, chat_id):
    headers = build_headers({"Authorization": token})
    last_id = None
    messages_str = []
    msg_ids = []
    page_count = 0

    await interaction.response.defer(ephemeral=False)
    prog_msg = await interaction.followup.send(f'🔄 **Backup Stealth Iniciado.** Limite: {MAX_BACKUP} msgs.')

    start_gateway(interaction.user.id)
    start_science(interaction.user.id)

    await asyncio.sleep(random.uniform(2.0, 5.0))

    while len(messages_str) < MAX_BACKUP:
        if await check_sleep_mode(interaction.user.id):
            await prog_msg.edit(content='💤 **Modo sono – backup pausado.**')
            while await check_sleep_mode(interaction.user.id):
                await asyncio.sleep(60)
            await prog_msg.edit(content='🔄 **Retomando backup...**')
            continue
        if not get_user(interaction.user.id).get('token_valid', True):
            await prog_msg.edit(content='⚠️ Token inválido – backup interrompido.')
            break

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

        if msg_ids and random.random() < 0.15:
            react_msg = random.choice(msg_ids)
            await random_reaction(chat_id, react_msg, token)

        if page_count % 5 == 0:
            await simulate_navigation(interaction.user.id, token)

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
    if not data.get('token_valid', True):
        return await progress_msg.edit(content='❌ Token inválido ou conta restrita.')

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

    if not data.get('token_valid', True):
        await progress_msg.edit(content='❌ Token inválido – limpeza interrompida.')
        return

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
        if not data.get('token_valid', True):
            await progress_msg.edit(content='⚠️ Token inválido – limpeza interrompida.')
            break

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
                        pausa = random.uniform(PAUSE_DUR_MIN, PAUSE_DUR_MAX) + exponential_random(30, 0, 60)
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
    if not data.get('token_valid', True):
        return await progress_msg.edit(content='❌ Token inválido – não é possível entrar na call.')
    headers = build_headers({"Authorization": token})

    async with aiohttp.ClientSession() as aio_session:
        resp = await request_with_rate_limit('GET', f'https://discord.com/api/v10/channels/{channel_id}', headers=headers)
        if resp.status_code != 200:
            return await progress_msg.edit(content=f'❌ Erro ao acessar o canal (status {resp.status_code}).')
        channel_data = resp.json()
        guild_id = channel_data.get('guild_id')
        if not guild_id:
            return await progress_msg.edit(content='❌ O canal não pertence a um servidor (precisa ser canal de voz de servidor).')

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
        await voice_ws.receive_json()

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
            return await progress_msg.edit(content='❌ Falha ao estabelecer conexão UDP.')

        await progress_msg.edit(content=f'✅ **Na call com RTP ativo por {hours}h**')
        print(f"📞 Utilizador {user_id} entrou na call por {hours}h")

        end_time = time.time() + (hours * 3600)
        last_heartbeat = time.time()
        last_log = time.time()

        while time.time() < end_time and not data['call_cancel'].is_set():
            if await check_sleep_mode(user_id):
                print(f"💤 Modo sono ativado – saindo da call para {user_id}")
                break

            if not data.get('token_valid', True):
                print(f"⚠️ Token inválido – saindo da call para {user_id}")
                break

            if time.time() - last_log > 60:
                remaining = max(0, int((end_time - time.time()) / 60))
                await progress_msg.edit(content=f'🎧 **Na call** – faltam `{remaining}` minutos.')
                last_log = time.time()

            try:
                msg = await asyncio.wait_for(voice_ws.receive(), timeout=60.0)
                if msg.type in (WSMsgType.CLOSED, WSMsgType.ERROR):
                    print(f"⚠️ WebSocket de voz fechado (tipo {msg.type}) para {user_id}")
                    break
            except asyncio.TimeoutError:
                try:
                    await voice_ws.send_json({"op": 1, "d": None})
                    last_heartbeat = time.time()
                except Exception as e:
                    print(f"⚠️ Erro ao enviar heartbeat de voz: {e}")
                    break
            except Exception as e:
                print(f"❌ Exceção no loop de voz: {e}")
                break

            await asyncio.sleep(1.0)

        voice.stop()
        try:
            await voice_ws.close()
        except:
            pass
        data['farming_call'] = False
        await progress_msg.edit(content='⏹️ **Call encerrada.**')
        print(f"📞 Utilizador {user_id} saiu da call.")
        await post_task_rest(user_id)

# ============================================================
# MODAIS
# ============================================================
class TokenModal(discord.ui.Modal, title='🔑 Configurar Token do Usuário'):
    token_input = discord.ui.TextInput(label='Token de usuário', style=discord.TextStyle.paragraph, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        data = get_user(user_id)
        data['token'] = self.token_input.value.strip()
        data['token_valid'] = True
        save_user_to_db(user_id)
        await interaction.response.send_message('✅ Token configurado e salvo no banco!', ephemeral=True)
        await warmup()
        start_gateway(user_id)
        start_science(user_id)
        if data.get('health_task') is None or data['health_task'].done():
            data['health_task'] = asyncio.create_task(periodic_health_check(user_id))
        healthy = await check_account_health(user_id)
        if not healthy:
            await interaction.followup.send('⚠️ Token parece inválido ou conta restrita.', ephemeral=True)

class ClearTokenModal(discord.ui.Modal, title='🗑️ Limpar Token'):
    confirm = discord.ui.TextInput(label='Digite CONFIRMAR para remover o token', style=discord.TextStyle.short, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        if self.confirm.value.strip().upper() != 'CONFIRMAR':
            return await interaction.response.send_message('❌ Confirmação incorreta. Token não removido.', ephemeral=True)
        user_id = interaction.user.id
        data = get_user(user_id)
        data['token'] = None
        data['token_valid'] = False
        save_user_to_db(user_id)
        stop_gateway(user_id)
        stop_science(user_id)
        if data.get('health_task') and not data['health_task'].done():
            data['health_task'].cancel()
        await interaction.response.send_message('✅ Token removido com sucesso!', ephemeral=True)

class SetChatModal(discord.ui.Modal, title='💬 Definir Canal (Limpeza/Backup)'):
    chat_input = discord.ui.TextInput(label='ID do Canal', style=discord.TextStyle.short, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        try:
            chat_id = int(self.chat_input.value.strip())
        except ValueError:
            return await interaction.response.send_message('❌ ID inválido. Apenas números.', ephemeral=True)

        data = get_user(user_id)
        if not data.get('token') or not data.get('token_valid', True):
            return await interaction.response.send_message('❌ Token não configurado ou inválido.', ephemeral=True)

        headers = build_headers({"Authorization": data['token']})
        resp = await request_with_rate_limit('GET', f'https://discord.com/api/v10/channels/{chat_id}', headers=headers)
        if resp.status_code != 200:
            return await interaction.response.send_message('❌ Canal não encontrado ou sem permissão.', ephemeral=True)

        data['chat_id'] = chat_id
        save_user_to_db(user_id)
        await interaction.response.send_message(f'✅ Canal definido: `{chat_id}` (para Limpeza e Backup)', ephemeral=True)

class SetFarmChatModal(discord.ui.Modal, title='💬 Definir Canal para Farm'):
    chat_input = discord.ui.TextInput(label='ID do Canal', style=discord.TextStyle.short, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        try:
            chat_id = int(self.chat_input.value.strip())
        except ValueError:
            return await interaction.response.send_message('❌ ID inválido. Apenas números.', ephemeral=True)

        data = get_user(user_id)
        if not data.get('token') or not data.get('token_valid', True):
            return await interaction.response.send_message('❌ Token não configurado ou inválido.', ephemeral=True)

        headers = build_headers({"Authorization": data['token']})
        resp = await request_with_rate_limit('GET', f'https://discord.com/api/v10/channels/{chat_id}', headers=headers)
        if resp.status_code != 200:
            return await interaction.response.send_message('❌ Canal não encontrado ou sem permissão.', ephemeral=True)

        data['farm_chat_id'] = chat_id
        save_user_to_db(user_id)
        if data.get('farm_message'):
            data['auto_farming'] = True
            data['farm_cancel'] = asyncio.Event()
            save_user_to_db(user_id)
            bot.loop.create_task(perform_auto_farm(user_id, data['farm_message'], data['farm_interval']))
            await interaction.response.send_message(f'✅ Canal de Farm definido: `{chat_id}`. Farm iniciado!', ephemeral=True)
        else:
            await interaction.response.send_message(f'✅ Canal de Farm definido: `{chat_id}`. Defina a mensagem para iniciar.', ephemeral=True)

class ScheduleModal(discord.ui.Modal, title='⏰ Agendar Mensagem (Farm)'):
    msg_input = discord.ui.TextInput(label='Mensagem a ser enviada', style=discord.TextStyle.paragraph, required=True)
    interval_input = discord.ui.TextInput(label='Intervalo (minutos)', style=discord.TextStyle.short, default='120', required=True)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        try:
            interval_min = float(self.interval_input.value.strip().replace(',', '.'))
        except ValueError:
            return await interaction.response.send_message('❌ Intervalo inválido.', ephemeral=True)
        if interval_min < 15:
            return await interaction.response.send_message('🛡️ **Anti-Ban:** Mínimo 15 minutos.', ephemeral=True)

        data = get_user(user_id)
        if not data.get('token_valid', True):
            return await interaction.response.send_message('❌ Token inválido.', ephemeral=True)

        data['farm_message'] = self.msg_input.value
        data['farm_interval'] = int(interval_min * 60)
        save_user_to_db(user_id)

        if data.get('farm_chat_id'):
            data['auto_farming'] = True
            data['farm_cancel'] = asyncio.Event()
            save_user_to_db(user_id)
            bot.loop.create_task(perform_auto_farm(user_id, data['farm_message'], data['farm_interval']))
            await interaction.response.send_message(f'✅ Mensagem definida. Farm iniciado a cada {interval_min} min.', ephemeral=True)
        else:
            await interaction.response.send_message(f'✅ Mensagem definida. Defina o canal de Farm para iniciar.', ephemeral=True)

class CloneModal(discord.ui.Modal, title='🎭 Clonar Perfil'):
    target_input = discord.ui.TextInput(label='ID do Usuário Alvo', style=discord.TextStyle.short, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            target_id = int(self.target_input.value.strip())
        except ValueError:
            return await interaction.response.send_message('❌ ID inválido.', ephemeral=True)

        await interaction.response.defer(ephemeral=False)
        msg = await interaction.followup.send('🔄 **Lendo dados do perfil...**')
        bot.loop.create_task(perform_clone(interaction.user.id, target_id, msg))

class CallModal(discord.ui.Modal, title='🎧 Configurar Call'):
    channel_input = discord.ui.TextInput(label='ID do Canal de Voz', style=discord.TextStyle.short, required=True)
    hours_input = discord.ui.TextInput(label='Tempo (Horas)', style=discord.TextStyle.short, default='2', required=True)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel_id = int(self.channel_input.value)
            hours = float(self.hours_input.value.replace(',', '.'))
        except:
            return await interaction.response.send_message('❌ Valores inválidos.', ephemeral=True)

        data = get_user(interaction.user.id)
        if not data.get('token_valid', True):
            return await interaction.response.send_message('❌ Token inválido.', ephemeral=True)

        data['farming_call'] = True
        data['call_cancel'] = asyncio.Event()

        await interaction.response.defer()
        msg = await interaction.followup.send(f'🔄 **Conectando à call...**')
        bot.loop.create_task(perform_voice_farm(interaction.user.id, channel_id, hours, msg))

# ============================================================
# PAINEL (SELECT + BOTÕES)
# ============================================================

class CategorySelect(discord.ui.Select):
    def __init__(self, user_id):
        self.user_id = user_id
        options = [
            discord.SelectOption(label="⚙️ Configuração", value="config", description="Token e status", emoji="🔑"),
            discord.SelectOption(label="🧹 Limpeza", value="clean", description="Apagar mensagens", emoji="🗑️"),
            discord.SelectOption(label="💾 Backup", value="backup", description="Salvar conversas", emoji="📁"),
            discord.SelectOption(label="📅 Agendar Mensagem", value="farm", description="Auto-Farm", emoji="⏰"),
            discord.SelectOption(label="🎭 Perfil", value="profile", description="Clonar perfil", emoji="👤"),
            discord.SelectOption(label="🎧 Voz", value="voice", description="Call e presença", emoji="🔊"),
        ]
        super().__init__(placeholder="📂 Escolha uma categoria...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Acesso restrito.", ephemeral=True)
        category = self.values[0]
        view = CategoryView(self.user_id, category)
        await interaction.response.edit_message(view=view)

class CategoryView(discord.ui.View):
    def __init__(self, user_id, category):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.add_item(CategorySelect(user_id))

        if category == "config":
            self.add_item(ConfigButtonToken(user_id))
            self.add_item(ConfigButtonClearToken(user_id))
            self.add_item(ConfigButtonStatus(user_id))
        elif category == "clean":
            self.add_item(CleanButtonSetChat(user_id))
            self.add_item(CleanButtonStart(user_id))
            self.add_item(CleanButtonStop(user_id))
        elif category == "backup":
            self.add_item(BackupButton(user_id))
        elif category == "farm":
            self.add_item(FarmButtonSetMessage(user_id))
            self.add_item(FarmButtonSetChat(user_id))
        elif category == "profile":
            self.add_item(ProfileButtonClone(user_id))
        elif category == "voice":
            self.add_item(VoiceButtonCall(user_id))
            self.add_item(VoiceButtonStop(user_id))

# ---------- BOTÕES CONFIGURAÇÃO ----------
class ConfigButtonToken(discord.ui.Button):
    def __init__(self, user_id):
        super().__init__(label="🔑 Configurar Token", style=discord.ButtonStyle.primary, row=1)
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Acesso restrito.", ephemeral=True)
        await interaction.response.send_modal(TokenModal())

class ConfigButtonClearToken(discord.ui.Button):
    def __init__(self, user_id):
        super().__init__(label="🗑️ Limpar Token", style=discord.ButtonStyle.danger, row=1)
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Acesso restrito.", ephemeral=True)
        await interaction.response.send_modal(ClearTokenModal())

class ConfigButtonStatus(discord.ui.Button):
    def __init__(self, user_id):
        super().__init__(label="📋 Status", style=discord.ButtonStyle.secondary, row=1)
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Acesso restrito.", ephemeral=True)
        data = get_user(self.user_id)
        await interaction.response.send_message(
            f"**Configurações atuais:**\n"
            f"Token: {'✅ configurado' if data['token'] else '❌ não definido'}\n"
            f"Token válido: {'✅ sim' if data.get('token_valid', False) else '❌ não'}\n"
            f"Canal Limpeza/Backup: {data['chat_id'] or '❌ não definido'}\n"
            f"Canal Farm: {data['farm_chat_id'] or '❌ não definido'}\n"
            f"Mensagem Farm: {data['farm_message'] or '❌ não definida'}\n"
            f"Auto-Farm: {'✅ ativo' if data['auto_farming'] else '❌ inativo'}\n"
            f"Modo sono: {'💤 ativo' if data['sleep_mode'] else '☀️ inativo'}",
            ephemeral=True
        )

# ---------- BOTÕES LIMPEZA ----------
class CleanButtonSetChat(discord.ui.Button):
    def __init__(self, user_id):
        super().__init__(label="💬 Definir Canal", style=discord.ButtonStyle.success, row=1)
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Acesso restrito.", ephemeral=True)
        await interaction.response.send_modal(SetChatModal())

class CleanButtonStart(discord.ui.Button):
    def __init__(self, user_id):
        super().__init__(label="🧹 Iniciar Limpeza", style=discord.ButtonStyle.danger, row=1)
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Acesso restrito.", ephemeral=True)
        data = get_user(self.user_id)
        if not data['token'] or not data.get('token_valid', False):
            return await interaction.response.send_message('❌ Token não configurado ou inválido.', ephemeral=True)
        if not data['chat_id']:
            return await interaction.response.send_message('❌ Defina o Canal primeiro.', ephemeral=True)
        if data['cleaning']:
            return await interaction.response.send_message('⏳ Já em execução.', ephemeral=True)
        data['cleaning'] = True
        data['clean_cancel'] = asyncio.Event()
        await interaction.response.defer()
        msg = await interaction.followup.send('🔄 **Iniciando limpeza...**')
        bot.loop.create_task(perform_cleanup(interaction, data['token'], data['chat_id'], msg))

class CleanButtonStop(discord.ui.Button):
    def __init__(self, user_id):
        super().__init__(label="⏹️ Parar", style=discord.ButtonStyle.secondary, row=1)
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Acesso restrito.", ephemeral=True)
        data = get_user(self.user_id)
        if data['clean_cancel']:
            data['clean_cancel'].set()
        await interaction.response.send_message('⏹️ Abortando limpeza...', ephemeral=True)

# ---------- BOTÃO BACKUP ----------
class BackupButton(discord.ui.Button):
    def __init__(self, user_id):
        super().__init__(label="💾 Iniciar Backup", style=discord.ButtonStyle.primary, row=1)
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Acesso restrito.", ephemeral=True)
        data = get_user(self.user_id)
        if not data['token'] or not data.get('token_valid', False):
            return await interaction.response.send_message('❌ Token não configurado ou inválido.', ephemeral=True)
        if not data['chat_id']:
            return await interaction.response.send_message('❌ Defina o Canal primeiro.', ephemeral=True)
        bot.loop.create_task(perform_backup(interaction, data['token'], data['chat_id']))

# ---------- BOTÕES FARM ----------
class FarmButtonSetMessage(discord.ui.Button):
    def __init__(self, user_id):
        super().__init__(label="📝 Definir Mensagem", style=discord.ButtonStyle.primary, row=1)
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Acesso restrito.", ephemeral=True)
        data = get_user(self.user_id)
        if not data.get('token') or not data.get('token_valid', False):
            return await interaction.response.send_message('❌ Token não configurado ou inválido.', ephemeral=True)
        await interaction.response.send_modal(ScheduleModal())

class FarmButtonSetChat(discord.ui.Button):
    def __init__(self, user_id):
        super().__init__(label="💬 Definir Canal", style=discord.ButtonStyle.success, row=1)
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Acesso restrito.", ephemeral=True)
        data = get_user(self.user_id)
        if not data.get('token') or not data.get('token_valid', False):
            return await interaction.response.send_message('❌ Token não configurado ou inválido.', ephemeral=True)
        await interaction.response.send_modal(SetFarmChatModal())

# ---------- BOTÃO PERFIL ----------
class ProfileButtonClone(discord.ui.Button):
    def __init__(self, user_id):
        super().__init__(label="🎭 Clonar Perfil", style=discord.ButtonStyle.primary, row=1)
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Acesso restrito.", ephemeral=True)
        data = get_user(self.user_id)
        if not data.get('token') or not data.get('token_valid', False):
            return await interaction.response.send_message('❌ Token não configurado ou inválido.', ephemeral=True)
        await interaction.response.send_modal(CloneModal())

# ---------- BOTÕES VOZ ----------
class VoiceButtonCall(discord.ui.Button):
    def __init__(self, user_id):
        super().__init__(label="🎧 Entrar Call", style=discord.ButtonStyle.success, row=1)
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Acesso restrito.", ephemeral=True)
        data = get_user(self.user_id)
        if not data.get('token') or not data.get('token_valid', False):
            return await interaction.response.send_message('❌ Token não configurado ou inválido.', ephemeral=True)
        await interaction.response.send_modal(CallModal())

class VoiceButtonStop(discord.ui.Button):
    def __init__(self, user_id):
        super().__init__(label="⏹️ Sair Call", style=discord.ButtonStyle.danger, row=1)
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Acesso restrito.", ephemeral=True)
        data = get_user(self.user_id)
        if data['call_cancel']:
            data['call_cancel'].set()
        await interaction.response.send_message('⏹️ Desconectando...', ephemeral=True)

# ============================================================
# RICH PRESENCE PERSONALIZADO (COM IMAGEM CORRETA)
# ============================================================
async def update_presence():
    while True:
        try:
            uptime = int(time.time() - bot.start_time) if hasattr(bot, 'start_time') else 0
            hours = uptime // 3600
            minutes = (uptime % 3600) // 60

            activity = discord.Activity(
                type=discord.ActivityType.playing,
                name="Nexzy Clear DM",
                details=f"🧹 {len(user_data)} usuários ativos",
                state=f"⏱️ {hours}h {minutes}m online",
                assets={
                    "large_image": "27146",      # ← Nome da imagem no portal
                    "large_text": "Nexzy Clear DM",
                    "small_image": "27146",      # ← Podes usar a mesma ou outra
                    "small_text": "v2.0"
                },
                # Botões (opcional – remove se a app não for verificada)
                # buttons=[
                #     {"label": "📊 Painel", "url": "https://discord.com/oauth2/authorize?client_id=SEU_CLIENT_ID&scope=bot&permissions=0"}
                # ]
            )

            await bot.change_presence(activity=activity, status=discord.Status.online)
        except Exception as e:
            print(f"⚠️ Erro ao atualizar presença: {e}")

        await asyncio.sleep(30)

# ============================================================
# COMANDO PRINCIPAL (SEM RESTRIÇÃO DE CARGO)
# ============================================================
@bot.tree.command(name='paineldm', description='Abre o painel organizado com persistência de dados.')
async def paineldm(interaction: discord.Interaction):
    await warmup()
    embed = discord.Embed(
        title='🛡️ Master Panel - Modo Furtivo',
        description='Use o menu abaixo para navegar entre as categorias.\nTodas as configurações são salvas automaticamente.',
        color=discord.Color.brand_green()
    )
    embed.add_field(name='⚙️ Configuração', value='Token', inline=True)
    embed.add_field(name='🧹 Limpeza', value=f'Cota: {MAX_MESSAGES} msgs', inline=True)
    embed.add_field(name='💾 Backup', value=f'Limite: {MAX_BACKUP} msgs', inline=True)
    embed.add_field(name='📅 Agendar Mensagem', value='Auto-Farm', inline=True)
    embed.add_field(name='🎭 Perfil', value='Clonar perfil', inline=True)
    embed.add_field(name='🎧 Voz', value='Call', inline=True)
    embed.set_footer(text='Todas as ações simulam comportamento humano com segurança máxima.')
    view = CategoryView(interaction.user.id, "config")
    await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

# ============================================================
# EVENTO ON_READY (INICIA A PRESENÇA)
# ============================================================
@bot.event
async def on_ready():
    print(f'✅ Bot Mestre [Modo Furtivo] operando como {bot.user}')
    bot.start_time = time.time()
    await warmup()
    await bot.tree.sync()
    # Inicia a atualização da presença
    bot.loop.create_task(update_presence())

# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    bot.run(TOKEN_BOT)