import json
import base64
import secrets
import random
import time
import math
import struct
from curl_cffi.requests import AsyncSession
from utils.logger import get_logger

logger = get_logger(__name__)

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

# Instância global (pode ser substituída por uma por usuário)
fingerprint_mgr = FingerprintManager()

# ============================================================
# SESSÃO HTTP GLOBAL
# ============================================================
session = AsyncSession(impersonate="chrome120")

# ============================================================
# CONSTRUTOR DE HEADERS
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

# ============================================================
# FUNÇÕES DE DISTRIBUIÇÃO PARA DELAYS REALISTAS
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
# REQUISIÇÕES COM RATE LIMIT ADAPTATIVO
# ============================================================
async def request_with_rate_limit(method: str, url: str, headers: dict = None, json_data: dict = None, **kwargs):
    if not headers:
        headers = build_headers()
    resp = await session.request(method, url, headers=headers, json=json_data, **kwargs)

    remaining = resp.headers.get('X-RateLimit-Remaining')
    reset_after = resp.headers.get('X-RateLimit-Reset-After')
    global_limit = resp.headers.get('X-RateLimit-Global')

    if resp.status_code == 429:
        retry_after = float(resp.headers.get('Retry-After', 5))
        if global_limit and global_limit.lower() == 'true':
            wait = retry_after + random.uniform(0.5, 2.0) + exponential_random(5, 0, 10)
        else:
            wait = retry_after + random.uniform(0.5, 1.5)
        await asyncio.sleep(wait)
        return await request_with_rate_limit(method, url, headers, json_data, **kwargs)

    if remaining is not None and int(remaining) < 5:
        wait = random.uniform(1.0, 5.0) + exponential_random(2, 0, 10)
        await asyncio.sleep(wait)

    return resp

# ============================================================
# SNOWFLAKE (NONCE)
# ============================================================
EPOCH = 1420070400000
_increment = 0

def generate_snowflake() -> int:
    global _increment
    _increment = (_increment + 1) & 0xFFF
    now = int(time.time() * 1000) - EPOCH
    return (now << 22) | (0 << 17) | (0 << 12) | _increment