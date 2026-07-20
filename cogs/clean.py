import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import time
from models.user import User
from utils.helpers import build_headers, request_with_rate_limit, normal_random, exponential_random
from utils.logger import get_logger

logger = get_logger(__name__)

# Constantes de segurança
MIN_DELAY = 15.0
MAX_DELAY = 35.0
PAUSE_AFTER = 20
PAUSE_DUR_MIN = 120.0
PAUSE_DUR_MAX = 180.0
MAX_MESSAGES = 150

class Clean(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_cleanups = {}  # user_id -> cancel_event

    @app_commands.command(name='clean', description='Limpa suas mensagens do canal configurado')
    @app_commands.describe(limit='Número máximo de mensagens a deletar (padrão: 150)')
    async def clean(self, interaction: discord.Interaction, limit: int = MAX_MESSAGES):
        await interaction.response.defer()
        user = User(interaction.user.id)
        token = user.get_token()
        if not token:
            await interaction.followup.send("❌ Nenhum token configurado. Use `/add_token`.")
            return

        chat_id = user.data.get('chat_id')
        if not chat_id:
            await interaction.followup.send("❌ Canal não definido. Use `/set_channel`.")
            return

        if limit > MAX_MESSAGES:
            await interaction.followup.send(f"❌ Limite máximo é {MAX_MESSAGES} mensagens.")
            return

        # Verifica se já há uma limpeza em andamento
        if interaction.user.id in self.active_cleanups:
            await interaction.followup.send("⏳ Você já tem uma limpeza em andamento. Use `/stop_clean` para interromper.")
            return

        msg = await interaction.followup.send(f"🔄 Iniciando limpeza de até {limit} mensagens...")

        cancel_event = asyncio.Event()
        self.active_cleanups[interaction.user.id] = cancel_event

        try:
            deleted = await self._perform_cleanup(interaction.user.id, token, chat_id, limit, msg, cancel_event)
            await msg.edit(content=f"✅ Limpeza concluída! {deleted} mensagens deletadas.")
        except asyncio.CancelledError:
            await msg.edit(content="⏹️ Limpeza interrompida pelo usuário.")
            raise
        finally:
            self.active_cleanups.pop(interaction.user.id, None)

    @app_commands.command(name='stop_clean', description='Interrompe a limpeza em andamento')
    async def stop_clean(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        if user_id not in self.active_cleanups:
            await interaction.response.send_message("❌ Você não tem uma limpeza em andamento.", ephemeral=True)
            return
        self.active_cleanups[user_id].set()
        await interaction.response.send_message("⏹️ Limpeza interrompida.", ephemeral=True)

    @app_commands.command(name='set_channel', description='Define o canal para limpeza e backup')
    @app_commands.describe(channel_id='ID do canal de texto')
    async def set_channel(self, interaction: discord.Interaction, channel_id: str):
        await interaction.response.defer()
        try:
            channel_id = int(channel_id)
        except ValueError:
            await interaction.followup.send("❌ ID inválido.")
            return

        user = User(interaction.user.id)
        token = user.get_token()
        if not token:
            await interaction.followup.send("❌ Token não configurado.")
            return

        headers = build_headers({"Authorization": token})
        resp = await request_with_rate_limit('GET', f'https://discord.com/api/v10/channels/{channel_id}', headers=headers)
        if resp.status_code != 200:
            await interaction.followup.send("❌ Canal não encontrado ou sem permissão.")
            return

        user.data['chat_id'] = channel_id
        user.save()
        await interaction.followup.send(f"✅ Canal definido: <#{channel_id}>")

    async def _perform_cleanup(self, user_id, token, chat_id, limit, progress_msg, cancel_event):
        headers = build_headers({"Authorization": token})
        deleted = 0
        last_id = None
        start_time = time.time()

        while deleted < limit:
            if cancel_event.is_set():
                raise asyncio.CancelledError()

            url = f"https://discord.com/api/v10/channels/{chat_id}/messages?limit=100"
            if last_id:
                url += f"&before={last_id}"

            resp = await request_with_rate_limit('GET', url, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"Erro ao buscar mensagens: {resp.status_code}")
                break

            msgs = resp.json()
            if not msgs:
                break

            for msg in msgs:
                if cancel_event.is_set():
                    raise asyncio.CancelledError()

                if msg['author']['id'] != str(user_id):
                    continue

                del_url = f"https://discord.com/api/v10/channels/{chat_id}/messages/{msg['id']}"
                del_resp = await request_with_rate_limit('DELETE', del_url, headers=headers)

                if del_resp.status_code == 204:
                    deleted += 1
                    if deleted % PAUSE_AFTER == 0:
                        pausa = random.uniform(PAUSE_DUR_MIN, PAUSE_DUR_MAX) + exponential_random(30, 0, 60)
                        await progress_msg.edit(content=f"⏸️ Pausa humana... {int(pausa)}s.")
                        await asyncio.sleep(pausa)
                    elif deleted % 3 == 0:
                        await progress_msg.edit(content=f"🔄 Limpeza: {deleted}/{limit}")

                # Delay realista entre deleções
                delay = normal_random((MIN_DELAY + MAX_DELAY) / 2, 5, min_val=MIN_DELAY, max_val=MAX_DELAY)
                await asyncio.sleep(delay)

                if deleted >= limit:
                    break

            last_id = msgs[-1]['id']

        elapsed = int(time.time() - start_time)
        logger.info(f"Limpeza concluída: {deleted} mensagens em {elapsed}s para user {user_id}")
        return deleted