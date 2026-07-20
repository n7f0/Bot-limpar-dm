import discord
from discord import app_commands
from discord.ext import commands
import asyncio
from models.user import User
from utils.helpers import generate_snowflake, build_headers, request_with_rate_limit, normal_random
from utils.logger import get_logger

logger = get_logger(__name__)

class Farm(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.farm_tasks = {}

    @app_commands.command(name='farm', description='Inicia auto-farm no canal configurado')
    @app_commands.describe(message='Mensagem a enviar', interval='Intervalo em minutos (mínimo 15)')
    async def farm(self, interaction: discord.Interaction, message: str, interval: int = 120):
        await interaction.response.defer()
        if interval < 15:
            await interaction.followup.send("❌ Intervalo mínimo é 15 minutos.")
            return

        user = User(interaction.user.id)
        token = user.get_token()
        if not token:
            await interaction.followup.send("❌ Token não configurado.")
            return
        chat_id = user.data.get('farm_chat_id') or user.data.get('chat_id')
        if not chat_id:
            await interaction.followup.send("❌ Canal de farm não definido. Use `/set_farm_channel`.")
            return

        # Salva configuração
        user.data['farm_message'] = message
        user.data['farm_interval'] = interval * 60
        user.data['auto_farming'] = 1
        user.save()

        # Inicia tarefa
        if interaction.user.id in self.farm_tasks:
            self.farm_tasks[interaction.user.id].cancel()

        task = asyncio.create_task(self._farm_loop(interaction.user.id, token, chat_id, message, interval * 60))
        self.farm_tasks[interaction.user.id] = task
        await interaction.followup.send(f"✅ Farm iniciado. Enviando a cada {interval} minutos.")

    async def _farm_loop(self, user_id, token, chat_id, message, interval):
        try:
            while True:
                headers = build_headers({"Authorization": token})
                payload = {'content': message, 'nonce': str(generate_snowflake())}
                await request_with_rate_limit('POST', f'https://discord.com/api/v10/channels/{chat_id}/messages',
                                              headers=headers, json_data=payload)
                delay = normal_random(interval, interval * 0.15, min_val=15)
                await asyncio.sleep(delay)
        except asyncio.CancelledError:
            logger.info(f"Farm cancelado para {user_id}")
        except Exception as e:
            logger.error(f"Erro no farm: {e}")

    @app_commands.command(name='stop_farm', description='Para o auto-farm')
    async def stop_farm(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        if user_id in self.farm_tasks:
            self.farm_tasks[user_id].cancel()
            del self.farm_tasks[user_id]
            user = User(user_id)
            user.data['auto_farming'] = 0
            user.save()
            await interaction.response.send_message("⏹️ Farm interrompido.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nenhum farm ativo.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Farm(bot))