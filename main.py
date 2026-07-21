import os
import asyncio
import logging
import json
import websockets
from curl_cffi.requests import AsyncSession

logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv('BOT_TOKEN')
session = AsyncSession(impersonate="chrome120")

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
            "intents": 33281,
            "properties": {
                "os": "Windows",
                "browser": "Chrome",
                "device": ""
            }
        }
    }
    await ws.send(json.dumps(payload))

async def handle_messages(ws, data):
    try:
        t = data.get("t")
        if t == "MESSAGE_CREATE":
            msg = data.get("d", {})
            content = msg.get("content", "").strip()
            channel_id = msg.get("channel_id")
            author = msg.get("author", {})
            user_id = author.get("id")

            # Evita responder a si mesmo ou a outros bots
            if user_id == "1523710047362879649" or author.get("bot"):
                return

            if content == "/paineldm":
                token_val = TOKEN.strip()
                auth_header = token_val if token_val.startswith("Bot ") else f"Bot {token_val}"
                headers = {
                    "Authorization": auth_header,
                    "Content-Type": "application/json"
                }

                # Envia o painel diretamente no canal do servidor onde o comando foi digitado
                msg_url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
                payload = {
                    "embeds": [
                        {
                            "title": "🛡️ Painel de Controle - Gerenciamento e Limpeza",
                            "description": "Utilize os botões abaixo para interagir com o sistema diretamente por este canal.",
                            "color": 5814783,
                            "fields": [
                                {"name": "Status do Servidor", "value": "🟢 Online e Operacional", "inline": True},
                                {"name": "Disponibilidade", "value": "24/7 Ativo", "inline": True}
                            ],
                            "footer": {"text": "Painel Público do Servidor"}
                        }
                    ],
                    "components": [
                        {
                            "type": 1,
                            "components": [
                                {
                                    "type": 2,
                                    "style": 1,
                                    "custom_id": "btn_limpar",
                                    "label": "🧹 Iniciar Ação",
                                    "disabled": False
                                }
                            ]
                        }
                    ]
                }
                
                res_msg = await session.post(msg_url, headers=headers, json=payload)
                logging.info(f"Painel fixo do servidor enviado com sucesso! Status HTTP: {res_msg.status_code}")

    except Exception as e:
        logging.error(f"Erro ao processar mensagem do painel: {e}")

async def start_discord_gateway():
    gateway_url = "wss://gateway.discord.gg/?v=10&encoding=json"

    while True:
        try:
            logging.info("🔌 Conectando ao Gateway do Discord via WebSocket puro...")
            async with websockets.connect(gateway_url) as ws:
                async for message in ws:
                    data = json.loads(message)
                    op = data.get("op")
                    d = data.get("d", {})

                    if op == 10:
                        heartbeat_interval = d.get("heartbeat_interval", 41300) / 1000.0
                        asyncio.create_task(send_heartbeat(ws, heartbeat_interval))
                        await send_identify(ws)

                    elif data.get("t") == "READY":
                        user = d.get('user', {})
                        logging.info(f"✅ Conectado com sucesso na API como {user.get('username')} (ID: {user.get('id')})!")

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
