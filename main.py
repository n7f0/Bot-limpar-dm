import os
import asyncio
import logging
import json
import websockets
from curl_cffi.requests import AsyncSession

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv('BOT_TOKEN')
session = AsyncSession(impersonate="chrome120")

voice_state_cache = {
    "guild_id": None,
    "channel_id": None,
    "session_id": None,
    "websocket": None
}

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
            "intents": 513,
            "properties": {
                "os": "Windows",
                "browser": "Chrome",
                "device": ""
            }
        }
    }
    await ws.send(json.dumps(payload))

async def keep_alive_udp_loop():
    while True:
        try:
            await asyncio.sleep(5)
            if voice_state_cache.get("channel_id"):
                logging.debug("Keep-alive de voz enviado.")
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(5)

async def start_discord_gateway():
    gateway_url = "wss://gateway.discord.gg/?v=10&encoding=json"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Pragma": "no-cache",
        "Cache-Control": "no-cache"
    }

    while True:
        try:
            logging.info("🔌 Conectando ao Gateway do Discord via WebSocket puro...")
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
                        await send_identify(ws)

                    elif t == "READY":
                        user = d.get('user', {})
                        logging.info(f"✅ Conectado com sucesso na API como {user.get('username')} (ID: {user.get('id')})!")

                    elif t == "VOICE_SERVER_UPDATE":
                        logging.info(f"🎙️ Endpoint de voz recebido com sucesso!")

        except Exception as e:
            logging.error(f"⚠️ Conexão perdida no Gateway: {e}. Reconectando em 5 segundos...")
            await asyncio.sleep(5)

if __name__ == "__main__":
    if not TOKEN:
        logging.error("❌ BOT_TOKEN não definido nas variáveis de ambiente.")
        exit(1)
    
    try:
        asyncio.run(start_discord_gateway())
    except KeyboardInterrupt:
        logging.info("Bot encerrado manualmente.")
