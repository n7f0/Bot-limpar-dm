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
            "intents": 33281,  # Intents incluindo mensagens e canais de voz
            "properties": {
                "os": "Windows",
                "browser": "Chrome",
                "device": ""
            }
        }
    }
    await ws.send(json.dumps(payload))

async def handle_messages(ws, data):
    """Gerencia as mensagens recebidas para responder ao comando !painel"""
    try:
        t = data.get("t")
        if t == "MESSAGE_CREATE":
            msg = data.get("d", {})
            content = msg.get("content", "")
            channel_id = msg.get("channel_id")
            author = msg.get("author", {})

            # Evita responder a si mesmo
            if author.get("id") == "1529128615155994787":
                return

            if content == "!painel":
                # Envia uma requisição HTTP para a API do Discord respondendo no chat
                url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
                headers = {
                    "Authorization": f"Bot {TOKEN}" if not TOKEN.startswith("MT") else TOKEN, # Suporte a token de usuário ou bot
                    "Content-Type": "application/json"
                }
                payload = {
                    "content": "🛡️ **Painel de Controle Ativo!**\nBot online e conectado via Gateway direto."
                }
                await session.post(url, headers=headers, json=payload)
                logging.info(f"Painel enviado via comando !painel no canal {channel_id}")
    except Exception as e:
      logging.error(f"Erro ao processar mensagem: {e}")

async def start_discord_gateway():
    gateway_url = "wss://gateway.discord.gg/?v=10&encoding=json"

    while True:
        try:
            logging.info("🔌 Conectando ao Gateway do Discord via WebSocket puro...")
            async with websockets.connect(gateway_url) as ws:
                voice_state_cache["websocket"] = ws

                async for message in ws:
                    data = json.loads(message)
                    op = data.get("op")
                    d = data.get("d", {})

                    if op == 10:  # Hello event
                        heartbeat_interval = d.get("heartbeat_interval", 41300) / 1000.0
                        asyncio.create_task(send_heartbeat(ws, heartbeat_interval))
                        await send_identify(ws)

                    elif data.get("t") == "READY":
                        user = d.get('user', {})
                        logging.info(f"✅ Conectado com sucesso na API como {user.get('username')} (ID: {user.get('id')})!")

                    # Processa eventos de mensagens e rede
                    asyncio.create_task(handle_messages(ws, data))

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
