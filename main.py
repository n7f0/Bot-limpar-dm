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

            if author.get("id") == "1529128615155994787":
                return

            if content == "/paineldm":
                url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
                
                # Tratamento de cabeçalho dependendo se é Bot Token puro ou Bearer/User Token
                auth_header = TOKEN if TOKEN.startswith("MT") or TOKEN.startswith("Bot ") else f"Bot {TOKEN}"
                if not auth_header.startswith("Bot ") and not TOKEN.startswith("MT"):
                    auth_header = f"Bot {TOKEN}"

                headers = {
                    "Authorization": auth_header,
                    "Content-Type": "application/json"
                }

                # Criando um Embed rico para o painel aparecer visualmente bonito
                payload = {
                    "embeds": [
                        {
                            "title": "🛡️ Painel de Controle - Gerenciamento DM",
                            "description": "Selecione uma das opções abaixo para gerenciar suas conversas e sistema.",
                            "color": 5814783,
                            "fields": [
                                {"name": "Status do Sistema", "value": "🟢 Conectado via Gateway Direto", "inline": False},
                                {"name": "ID da Conta", "value": "`1529128615155994787`", "inline": True},
                                {"name": "Modo", "value": "Estável 24/7", "inline": True}
                            ],
                            "footer": {
                                "text": "Sistema de Controle Automático"
                            }
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
                                    "label": "🧹 Limpar DMs",
                                    "disabled": False
                                },
                                {
                                    "type": 2,
                                    "style": 4,
                                    "custom_id": "btn_status",
                                    "label": "📊 Atualizar Status",
                                    "disabled": False
                                }
                            ]
                        }
                    ]
                }

                response = await session.post(url, headers=headers, json=payload)
                logging.info(f"Painel visual enviado com sucesso! Status HTTP: {response.status_code}")
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
