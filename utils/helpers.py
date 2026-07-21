import asyncio
import aiohttp
import logging
import random
import os
import time
import base64

logger = logging.getLogger(__name__)

# ========== OBTER ID DO USUÁRIO ==========
async def get_user_id_from_token(token: str) -> str:
    headers = {'Authorization': token}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get('https://discord.com/api/v9/users/@me', headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data['id']
        except:
            pass
    return None

# ========== LIMPEZA FURTIVA ==========
async def stealth_clear(token: str, channel_id: int, limit: int = 150):
    user_id = await get_user_id_from_token(token)
    if not user_id:
        return 0, 0

    headers = {'Authorization': token}
    deleted = 0
    failed = 0
    batch_size = 20
    total_limit = limit

    async with aiohttp.ClientSession() as session:
        url = f'https://discord.com/api/v9/channels/{channel_id}/messages?limit=100'
        while deleted < total_limit:
            try:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 429:
                        retry = (await resp.json()).get('retry_after', 5)
                        await asyncio.sleep(retry + 1)
                        continue
                    if resp.status != 200:
                        break
                    messages = await resp.json()
                    if not messages:
                        break

                    own_msgs = [m for m in messages if m['author']['id'] == user_id]
                    if not own_msgs:
                        if len(messages) < 100:
                            break
                        last_id = messages[-1]['id']
                        url = f'https://discord.com/api/v9/channels/{channel_id}/messages?limit=100&before={last_id}'
                        continue

                    for i in range(0, min(len(own_msgs), total_limit - deleted), batch_size):
                        batch = own_msgs[i:i+batch_size]
                        for msg in batch:
                            del_url = f'https://discord.com/api/v9/channels/{channel_id}/messages/{msg["id"]}'
                            async with session.delete(del_url, headers=headers) as del_resp:
                                if del_resp.status == 204:
                                    deleted += 1
                                elif del_resp.status == 429:
                                    retry = (await del_resp.json()).get('retry_after', 2)
                                    await asyncio.sleep(retry + 0.5)
                                else:
                                    failed += 1
                            await asyncio.sleep(random.uniform(0.8, 1.8))

                        if deleted < total_limit:
                            await asyncio.sleep(random.uniform(15, 35))

                    if len(messages) < 100:
                        break
                    last_id = messages[-1]['id']
                    url = f'https://discord.com/api/v9/channels/{channel_id}/messages?limit=100&before={last_id}'

            except Exception as e:
                logger.error(f"Erro no stealth clear: {e}")
                break

    return deleted, failed

# ========== BACKUP STEALTH ==========
async def stealth_backup(token: str, channel_id: int, limit: int = 3000):
    user_id = await get_user_id_from_token(token)
    if not user_id:
        return None, 0

    headers = {'Authorization': token}
    messages = []
    url = f'https://discord.com/api/v9/channels/{channel_id}/messages?limit=100'

    async with aiohttp.ClientSession() as session:
        while len(messages) < limit:
            try:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 429:
                        retry = (await resp.json()).get('retry_after', 5)
                        await asyncio.sleep(retry + 1)
                        continue
                    if resp.status != 200:
                        break
                    data = await resp.json()
                    if not data:
                        break
                    messages.extend(data)
                    for msg in data:
                        await asyncio.sleep(random.uniform(0.2, 0.6))
                    if random.random() < 0.3:
                        emojis = ['👀', '📖', '✅', '📌', '🔍']
                        for msg in random.sample(data, min(3, len(data))):
                            react_url = f'https://discord.com/api/v9/channels/{channel_id}/messages/{msg["id"]}/reactions/{random.choice(emojis)}/%40me'
                            async with session.put(react_url, headers=headers) as r:
                                pass
                    if len(data) < 100:
                        break
                    last_id = data[-1]['id']
                    url = f'https://discord.com/api/v9/channels/{channel_id}/messages?limit=100&before={last_id}'
            except:
                break

    filename = f'/app/data/backup_{channel_id}_{int(time.time())}.txt'
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w', encoding='utf-8') as f:
        for msg in messages:
            f.write(f"[{msg['timestamp']}] {msg['author']['username']}: {msg.get('content', '')}\n")
    return filename, len(messages)

# ========== AGENDAR MENSAGEM ==========
async def schedule_message(token: str, channel_id: int, content: str, minutes: int):
    await asyncio.sleep(minutes * 60)
    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    async with aiohttp.ClientSession() as session:
        typing_url = f'https://discord.com/api/v9/channels/{channel_id}/typing'
        await session.post(typing_url, headers=headers)
        await asyncio.sleep(random.uniform(1.0, 3.0))
        payload = {'content': content}
        send_url = f'https://discord.com/api/v9/channels/{channel_id}/messages'
        async with session.post(send_url, headers=headers, json=payload) as resp:
            return resp.status == 200

# ========== AUTO-FARM COM REPETIÇÕES ==========
async def auto_farm(token: str, channel_id: str, messages: list, interval_seconds: int = 60, repeats: int = 0):
    """
    Envia mensagens repetidamente com intervalo em segundos.
    Se repeats=0, repete infinitamente.
    """
    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    sent = 0
    total = repeats if repeats > 0 else float('inf')

    async with aiohttp.ClientSession() as session:
        while sent < total:
            for msg in messages:
                if sent >= total:
                    break
                typing_url = f'https://discord.com/api/v9/channels/{channel_id}/typing'
                await session.post(typing_url, headers=headers)
                await asyncio.sleep(random.uniform(1.0, 2.0))
                payload = {'content': msg}
                send_url = f'https://discord.com/api/v9/channels/{channel_id}/messages'
                async with session.post(send_url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        sent += 1
                    else:
                        logger.warning(f"Falha ao enviar mensagem: {resp.status}")
                await asyncio.sleep(random.uniform(0.5, 1.5))
            if sent >= total:
                break
            # Aguarda o intervalo antes do próximo ciclo
            await asyncio.sleep(interval_seconds)

# ========== CLONAR PERFIL ==========
async def clone_profile(token: str, target_user_id: str):
    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    async with aiohttp.ClientSession() as session:
        async with session.get(f'https://discord.com/api/v9/users/{target_user_id}', headers=headers) as resp:
            if resp.status != 200:
                return False, "Usuário não encontrado"
            target_data = await resp.json()

        avatar_hash = target_data.get('avatar')
        if avatar_hash:
            avatar_url = f"https://cdn.discordapp.com/avatars/{target_user_id}/{avatar_hash}.png?size=128"
            async with session.get(avatar_url) as img_resp:
                if img_resp.status == 200:
                    image_data = await img_resp.read()
                    b64 = base64.b64encode(image_data).decode('utf-8')
                    payload = {'avatar': f'data:image/png;base64,{b64}'}
                    async with session.patch('https://discord.com/api/v9/users/@me', headers=headers, json=payload) as patch:
                        pass

        bio = target_data.get('bio', '')
        if bio:
            payload = {'bio': bio}
            async with session.patch('https://discord.com/api/v9/users/@me/profile', headers=headers, json=payload) as patch:
                pass

        return True, "Perfil clonado (avatar e biografia)"