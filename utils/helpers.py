import asyncio
import aiohttp
import logging
import random
import time
import os
import base64
from datetime import datetime

logger = logging.getLogger(__name__)

# ========== AUXILIAR: OBTER ID DO USUÁRIO A PARTIR DO TOKEN ==========
async def get_user_id_from_token(token: str) -> str:
    """Retorna o ID do usuário dono do token."""
    headers = {'Authorization': token}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get('https://discord.com/api/v9/users/@me', headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data['id']
        except Exception as e:
            logger.error(f"Erro ao obter ID do usuário: {e}")
    return None

# ========== LIMPEZA FURTIVA ==========
async def stealth_clear(token: str, channel_id: int, limit: int = 150):
    """
    Apaga mensagens próprias com delays aleatórios (15‑35s entre lotes),
    pausas longas a cada 20 mensagens. Retorna (deletadas, falhas).
    """
    user_id = await get_user_id_from_token(token)
    if not user_id:
        logger.error("Não foi possível obter o ID do usuário para limpeza.")
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
                        logger.warning(f"Rate limit na busca: esperando {retry}s")
                        await asyncio.sleep(retry + 1)
                        continue
                    if resp.status != 200:
                        logger.error(f"Erro ao buscar mensagens: {resp.status}")
                        break
                    messages = await resp.json()
                    if not messages:
                        break

                    # Filtra apenas mensagens do próprio usuário
                    own_msgs = [m for m in messages if m['author']['id'] == user_id]
                    if not own_msgs:
                        if len(messages) < 100:
                            break
                        last_id = messages[-1]['id']
                        url = f'https://discord.com/api/v9/channels/{channel_id}/messages?limit=100&before={last_id}'
                        continue

                    # Apaga em lotes de até batch_size
                    for i in range(0, min(len(own_msgs), total_limit - deleted), batch_size):
                        batch = own_msgs[i:i+batch_size]
                        for msg in batch:
                            del_url = f'https://discord.com/api/v9/channels/{channel_id}/messages/{msg["id"]}'
                            async with session.delete(del_url, headers=headers) as del_resp:
                                if del_resp.status == 204:
                                    deleted += 1
                                    logger.debug(f"Apagada mensagem {msg['id']}")
                                elif del_resp.status == 429:
                                    retry = (await del_resp.json()).get('retry_after', 2)
                                    logger.warning(f"Rate limit ao apagar: esperando {retry}s")
                                    await asyncio.sleep(retry + 0.5)
                                else:
                                    failed += 1
                                    logger.warning(f"Falha ao apagar mensagem {msg['id']}: {del_resp.status}")
                            await asyncio.sleep(random.uniform(0.8, 1.8))

                        # Pausa longa a cada lote
                        if deleted < total_limit:
                            pause = random.uniform(15, 35)
                            logger.debug(f"Pausa de {pause:.1f}s entre lotes")
                            await asyncio.sleep(pause)

                    # Avança para próxima página
                    if len(messages) < 100:
                        break
                    last_id = messages[-1]['id']
                    url = f'https://discord.com/api/v9/channels/{channel_id}/messages?limit=100&before={last_id}'

            except Exception as e:
                logger.error(f"Erro no stealth clear: {e}")
                break

    logger.info(f"Limpeza furtiva concluída: {deleted} deletadas, {failed} falhas")
    return deleted, failed

# ========== BACKUP STEALTH ==========
async def stealth_backup(token: str, channel_id: int, limit: int = 3000):
    """
    Lê até 3000 mensagens, salva em .txt, simula leitura com pausas,
    envia ACKs (marca como lidas) e reage com emojis aleatórios.
    Retorna caminho do arquivo e número de mensagens lidas.
    """
    user_id = await get_user_id_from_token(token)
    if not user_id:
        logger.error("Não foi possível obter o ID do usuário para backup.")
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
                        logger.warning(f"Rate limit no backup: esperando {retry}s")
                        await asyncio.sleep(retry + 1)
                        continue
                    if resp.status != 200:
                        logger.error(f"Erro ao buscar mensagens para backup: {resp.status}")
                        break
                    data = await resp.json()
                    if not data:
                        break
                    messages.extend(data)

                    # Simula leitura (ACK) com pausas
                    for msg in data:
                        await asyncio.sleep(random.uniform(0.2, 0.6))

                    # Reage com emoji aleatório em algumas mensagens
                    if random.random() < 0.3:
                        emojis = ['👀', '📖', '✅', '📌', '🔍']
                        sample_size = min(3, len(data))
                        for msg in random.sample(data, sample_size):
                            emoji = random.choice(emojis)
                            react_url = f'https://discord.com/api/v9/channels/{channel_id}/messages/{msg["id"]}/reactions/{emoji}/%40me'
                            async with session.put(react_url, headers=headers) as r:
                                if r.status != 204:
                                    logger.debug(f"Falha ao reagir a mensagem {msg['id']}: {r.status}")

                    if len(data) < 100:
                        break
                    last_id = data[-1]['id']
                    url = f'https://discord.com/api/v9/channels/{channel_id}/messages?limit=100&before={last_id}'
            except Exception as e:
                logger.error(f"Erro no backup: {e}")
                break

    # Salvar em .txt
    filename = f'/app/data/backup_{channel_id}_{int(time.time())}.txt'
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w', encoding='utf-8') as f:
        for msg in messages:
            f.write(f"[{msg['timestamp']}] {msg['author']['username']}: {msg.get('content', '')}\n")
    
    logger.info(f"Backup concluído: {len(messages)} mensagens salvas em {filename}")
    return filename, len(messages)

# ========== AGENDAR MENSAGEM ==========
async def schedule_message(token: str, channel_id: int, content: str, minutes: int):
    """Envia mensagem após X minutos com simulação de digitação."""
    await asyncio.sleep(minutes * 60)
    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    async with aiohttp.ClientSession() as session:
        # Simular digitação
        typing_url = f'https://discord.com/api/v9/channels/{channel_id}/typing'
        try:
            await session.post(typing_url, headers=headers)
            await asyncio.sleep(random.uniform(1.0, 3.0))
        except Exception as e:
            logger.error(f"Erro ao simular digitação: {e}")

        payload = {'content': content}
        send_url = f'https://discord.com/api/v9/channels/{channel_id}/messages'
        try:
            async with session.post(send_url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    logger.info(f"Mensagem agendada enviada com sucesso: {content[:50]}...")
                    return True
                else:
                    logger.error(f"Falha ao enviar mensagem agendada: {resp.status}")
                    return False
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem agendada: {e}")
            return False

# ========== AUTO-FARM ==========
async def auto_farm(token: str, channel_id: int, messages: list, interval_min: int = 15, jitter: int = 5):
    """
    Envia mensagens/comandos repetidamente (intervalo mínimo 15 min, padrão 120 min)
    com jitter e simulação de digitação. Roda até ser cancelada.
    """
    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    async with aiohttp.ClientSession() as session:
        while True:
            for msg in messages:
                # Simular digitação
                typing_url = f'https://discord.com/api/v9/channels/{channel_id}/typing'
                try:
                    await session.post(typing_url, headers=headers)
                    await asyncio.sleep(random.uniform(1.0, 2.5))
                except Exception as e:
                    logger.error(f"Erro ao simular digitação no farm: {e}")

                payload = {'content': msg}
                send_url = f'https://discord.com/api/v9/channels/{channel_id}/messages'
                try:
                    async with session.post(send_url, headers=headers, json=payload) as resp:
                        if resp.status != 200:
                            logger.warning(f"Falha ao enviar mensagem no farm: {resp.status}")
                except Exception as e:
                    logger.error(f"Erro ao enviar mensagem no farm: {e}")

                await asyncio.sleep(random.uniform(2, 5))

            # Espera o intervalo com jitter
            base_interval = max(15, interval_min)
            jitter_seconds = random.randint(0, jitter * 60)
            wait_time = base_interval * 60 + jitter_seconds
            logger.debug(f"Farm: aguardando {wait_time//60}min {wait_time%60}s")
            await asyncio.sleep(wait_time)

# ========== CLONAR PERFIL ==========
async def clone_profile(token: str, target_user_id: str):
    """Copia avatar e biografia de outro usuário."""
    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    async with aiohttp.ClientSession() as session:
        # Obter dados do alvo
        async with session.get(f'https://discord.com/api/v9/users/{target_user_id}', headers=headers) as resp:
            if resp.status != 200:
                return False, "Usuário não encontrado"
            target_data = await resp.json()

        # Atualizar avatar (baixar e enviar)
        avatar_hash = target_data.get('avatar')
        if avatar_hash:
            avatar_url = f"https://cdn.discordapp.com/avatars/{target_user_id}/{avatar_hash}.png?size=128"
            try:
                async with session.get(avatar_url) as img_resp:
                    if img_resp.status == 200:
                        image_data = await img_resp.read()
                        b64 = base64.b64encode(image_data).decode('utf-8')
                        payload = {'avatar': f'data:image/png;base64,{b64}'}
                        async with session.patch('https://discord.com/api/v9/users/@me', headers=headers, json=payload) as patch:
                            if patch.status != 200:
                                logger.warning(f"Falha ao atualizar avatar: {patch.status}")
                    else:
                        logger.warning(f"Não foi possível baixar o avatar do alvo: {img_resp.status}")
            except Exception as e:
                logger.error(f"Erro ao clonar avatar: {e}")

        # Atualizar biografia (sobre)
        bio = target_data.get('bio', '')
        if bio:
            payload = {'bio': bio}
            try:
                async with session.patch('https://discord.com/api/v9/users/@me/profile', headers=headers, json=payload) as patch:
                    if patch.status != 200:
                        logger.warning(f"Falha ao atualizar biografia: {patch.status}")
            except Exception as e:
                logger.error(f"Erro ao clonar biografia: {e}")

        return True, "Perfil clonado com sucesso (avatar e biografia)"

# ========== ENTRAR EM CALL (via discord.py) ==========
# Esta função não é usada diretamente, pois a conexão de voz é feita via cog com o bot.
# Mantemos apenas como placeholder.