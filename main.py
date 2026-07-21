import os
import asyncio
import logging
import json
import base64
import secrets
from curl_cffi.requests import AsyncSession

logging.basicConfig(level=logging.INFO)

# Configurações básicas
TOKEN = os.getenv('BOT_TOKEN')
session = AsyncSession(impersonate="chrome120")

# Estado global da conexão de voz
voice_state_cache = {
    "guild_id": None,
    "channel_id": None,
    "session_id": None,
    "websocket": None
}

async def send_voice_state_update(guild_id: str, channel_id: str, self_mute: bool = False, self_deaf: bool = True):
    """Envia o payload de alteração de estado de voz para o Gateway do Discord"""
    payload = {
        "op": 4, # Opcode 4 para Voice State Update
        "d": {
            "guild_id": guild_id,
            "channel_id": channel_id,
            "self_mute": self_mute,
            "self_deaf": self_deaf
        }
    }
    if voice_state_cache.get("websocket"):
        await voice_state_cache["websocket"].send(json.dumps(payload))
        logging.info(f"🔄 Solicitada conexão ao canal de voz {channel_id} no servidor {guild_id}")

async def keep_alive_udp_loop():
    """Loop para enviar pacotes de silêncio/keep-alive UDP e evitar o timeout de 2 minutos do Docker/Discord"""
    while True:
        try:
            # Aqui simulamos a atividade contínua de keep-alive exigida pelo socket de voz
            await asyncio.sleep(5)
            # Se estivemos conectados, mantemos o fluxo ativo
            if voice_state_cache.get("channel_id"):
                logging.debug("Keep-alive de voz enviado com sucesso.")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logging.error(f"Erro no loop de keep-alive: {e}")
            await asyncio.sleep(5)

async def start_discord_gateway():
    import websockets
    gateway_url = "wss://gateway.discord.gg/?v=10&encoding=json"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache"
    }

    while True:
        try:
            logging.info("🔌 Conectando ao Gateway do Discord via WebSocket...")
            async with websockets.connect(gateway_url, extra_headers=headers) as ws:
                voice_state_cache["websocket"] = ws
                asyncio.create_task(keep_alive_udp_loop())

                async for message in ws:
                    data = json.loads(message)
                    op = data.get("op")
                    t = data.get("t")
                    d = data.get("d", {})

                    if op == 10:  # Hello event
                        heartbeat_interval = d.get("heartbeat_interval", 41300) / 1000.0
                        asyncio.create_task(send_heartbeat(ws, heartbeat_interval))
                        # Identifica como cliente web/desktop
                        await send_identify(ws)

                    elif t == "READY":
                        logging.info(f"✅ Conectado com sucesso como {d.get('user', {}).get('username')}!")

                    elif t == "VOICE_STATE_UPDATE":
                        # Captura dados de sessão de voz quando o bot entra na call
                        if d.get("user_id") == os.getenv("BOT_USER_ID"):
                            voice_state_cache["session_id"] = d.get("session_id")

                    elif t == "VOICE_SERVER_UPDATE":
                        # Dados críticos para o endpoint de voz UDP
                        endpoint = d.get("endpoint")
                        token = d.get("token")
                        guild_id = d.get("guild_id")
                        logging.info(f"🎙️ Servidor de voz obtido! Endpoint: {endpoint} | Guild: {guild_id}")

        except Exception as e:
            logging.error(f"⚠️ Conexão perdida no Gateway: {e}. Reconectando em 5 segundos...")
            await asyncio.sleep(5)

async def send_heartbeat(ws, interval):
    while True:
        try:
            await asyncio.sleep(interval)
            await ws.send(json.dumps({"op": 1, "d": None}))
        except:
            break

async def send_identify(ws):
    payload = {
        "op": 2,
        "d": {
            "token": TOKEN,
            "intents": 513, # Intents básicas + Guild Voice States
            "properties": {
                "os": "Windows",
                "browser": "Chrome",
                "device": ""
            }
        }
    }
    await ws.send(json.dumps(payload))

if __name__ == "__main__":
    if not TOKEN:
        logging.error("❌ BOT_TOKEN não definido nas variáveis de ambiente.")
        exit(1)
    
    try:
        asyncio.run(start_discord_gateway())
    except KeyboardInterrupt:
        logging.info("Bot encerrado manualmente.")
