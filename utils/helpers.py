import asyncio
import aiohttp
import logging

logger = logging.getLogger(__name__)

async def clear_dm_messages(token: str, channel_id: int, limit: int = 500, delay: float = 0.8):
    """
    Apaga mensagens em um canal DM usando token do usuário.
    Retorna o número de mensagens deletadas e uma lista de IDs que falharam.
    """
    headers = {
        'Authorization': token,
        'Content-Type': 'application/json'
    }
    
    deleted = 0
    failed_ids = []
    async with aiohttp.ClientSession() as session:
        url = f'https://discord.com/api/v9/channels/{channel_id}/messages?limit=100'
        
        while deleted < limit:
            try:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 429:
                        retry_after = (await resp.json()).get('retry_after', 5)
                        await asyncio.sleep(retry_after + 0.5)
                        continue
                    
                    if resp.status != 200:
                        logger.error(f"Erro ao buscar mensagens: {resp.status} - {await resp.text()}")
                        break
                    
                    messages = await resp.json()
                    if not messages:
                        break
                    
                    for msg in messages:
                        if deleted >= limit:
                            break
                        
                        msg_id = msg['id']
                        delete_url = f'https://discord.com/api/v9/channels/{channel_id}/messages/{msg_id}'
                        
                        async with session.delete(delete_url, headers=headers) as del_resp:
                            if del_resp.status == 429:
                                retry_after = (await del_resp.json()).get('retry_after', 2)
                                await asyncio.sleep(retry_after + 0.5)
                                continue
                            
                            if del_resp.status == 204:
                                deleted += 1
                            else:
                                failed_ids.append(msg_id)
                                logger.warning(f"Falha ao apagar {msg_id}: {del_resp.status}")
                        
                        await asyncio.sleep(delay)
                    
                    if len(messages) == 100 and deleted < limit:
                        last_id = messages[-1]['id']
                        url = f'https://discord.com/api/v9/channels/{channel_id}/messages?limit=100&before={last_id}'
                    else:
                        break
                        
            except Exception as e:
                logger.error(f"Erro na requisição: {e}")
                break
    
    return deleted, failed_ids

async def test_user_token(token: str) -> bool:
    """Verifica se o token é válido."""
    headers = {'Authorization': token}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get('https://discord.com/api/v9/users/@me', headers=headers) as resp:
                return resp.status == 200
        except:
            return False