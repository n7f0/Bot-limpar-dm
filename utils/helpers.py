import asyncio
import aiohttp
import logging
import random
import time
import base64
import json
from utils.db import save_user_data, get_user_data

logger = logging.getLogger(__name__)

def get_human_headers(token: str):
    x_super = {
        "os": "Windows",
        "browser": "Chrome",
        "device": "",
        "system_locale": "pt-BR",
        "browser_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "browser_version": "120.0.0.0",
        "os_version": "10",
        "referrer": "",
        "referring_domain": "",
        "referring_domain_current": "",
        "release_channel": "stable",
        "client_build_number": 255273,
        "client_event_source": None
    }
    encoded_props = base64.b64encode(json.dumps(x_super).encode()).decode()
    return {
        'Authorization': token,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'X-Super-Properties': encoded_props,
        'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7'
    }

async def send_webhook_notification(user_id: int, title: str, description: str, color: int = 0x00ff00):
    data = get_user_data(user_id)
    url = data.get('webhook_url')
    if not url: return

    embed = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    }
    async with aiohttp.ClientSession() as session:
        try:
            await session.post(url, json={"embeds": [embed]})
        except Exception as e:
            logger.error(f"Erro ao enviar webhook: {e}")

async def get_user_id_from_token(token: str) -> str:
    headers = get_human_headers(token)
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get('https://discord.com/api/v9/users/@me', headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data['id']
        except Exception as e:
            logger.error(f"Erro token check: {e}")
    return None

async def stealth_clear(token: str, channel_id: int, user_id_bot: int, limit: int = 150):
    user_id = await get_user_id_from_token(token)
    if not user_id: return 0, 0

    headers = get_human_headers(token)
    deleted = 0
    failed = 0
    db_data = get_user_data(user_id_bot)

    try:
        async with aiohttp.ClientSession() as session:
            url = f'https://discord.com/api/v9/channels/{channel_id}/messages?limit=100'
            while deleted < limit:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 429:
                        retry = (await resp.json()).get('retry_after', 5)
                        logger.warning(f"Rate limit hit! Sleeping for {retry}s")
                        await asyncio.sleep(retry + random.uniform(1.0, 3.0))
                        continue
                    if resp.status != 200: break
                    messages = await resp.json()
                    if not messages: break

                own_msgs = [m for m in messages if m['author']['id'] == user_id]
                if not own_msgs:
                    if len(messages) < 100: break
                    url = f'https://discord.com/api/v9/channels/{channel_id}/messages?limit=100&before={messages[-1]["id"]}'
                    continue

                for msg in own_msgs:
                    if deleted >= limit: break
                    del_url = f'https://discord.com/api/v9/channels/{channel_id}/messages/{msg["id"]}'
                    
                    async with session.delete(del_url, headers=headers) as del_resp:
                        if del_resp.status == 204:
                            deleted += 1
                            db_data['stats_cleared'] += 1
                        elif del_resp.status == 429:
                            retry = (await del_resp.json()).get('retry_after', 3)
                            await asyncio.sleep(retry + random.uniform(2.0, 5.0))
                        else:
                            failed += 1
                    
                    await asyncio.sleep(random.uniform(1.2, 3.5))
                
                save_user_data(user_id_bot, stats_cleared=db_data['stats_cleared'])

                if len(messages) < 100: break
                url = f'https://discord.com/api/v9/channels/{channel_id}/messages?limit=100&before={messages[-1]["id"]}'
                
    except asyncio.CancelledError:
        logger.info("Task de limpeza cancelada pelo usuário.")
        await send_webhook_notification(user_id_bot, "🧹 Limpeza Parada", f"Limpou {deleted} mensagens.", 0xff0000)
        raise

    await send_webhook_notification(user_id_bot, "✅ Limpeza Concluída", f"Total apagado: {deleted}", 0x00ff00)
    return deleted, failed

async def auto_farm(token: str, channel_id: int, user_id_bot: int, messages: list, interval_min: int = 15):
    headers = get_human_headers(token)
    headers['Content-Type'] = 'application/json'
    db_data = get_user_data(user_id_bot)
    
    try:
        async with aiohttp.ClientSession() as session:
            while True:
                for msg in messages:
                    typing_url = f'https://discord.com/api/v9/channels/{channel_id}/typing'
                    await session.post(typing_url, headers=headers)
                    await asyncio.sleep(random.uniform(1.5, 4.0)) 
                    
                    payload = {'content': msg}
                    send_url = f'https://discord.com/api/v9/channels/{channel_id}/messages'
                    async with session.post(send_url, headers=headers, json=payload) as resp:
                        if resp.status == 200:
                            db_data['stats_farmed'] += 1
                            save_user_data(user_id_bot, stats_farmed=db_data['stats_farmed'])
                    await asyncio.sleep(random.uniform(3, 7))

                base_interval = interval_min * 60
                jitter = random.randint(0, int(base_interval * 0.2)) 
                await asyncio.sleep(base_interval + jitter)
    except asyncio.CancelledError:
        logger.info("Task de farm cancelada pelo usuário.")
        await send_webhook_notification(user_id_bot, "🛑 Farm Parado", f"Status: Paralisado.", 0xff0000)
        raise
