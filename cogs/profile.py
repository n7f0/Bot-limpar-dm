import discord
from discord import app_commands
from discord.ext import commands
import base64
import asyncio
from models.user import User
from utils.helpers import build_headers, request_with_rate_limit
from utils.logger import get_logger

logger = get_logger(__name__)

class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='clone', description='Clona avatar e bio de outro usuário')
    @app_commands.describe(target_id='ID do usuário alvo')
    async def clone(self, interaction: discord.Interaction, target_id: str):
        await interaction.response.defer()
        try:
            target_id = int(target_id)
        except ValueError:
            await interaction.followup.send("❌ ID inválido.")
            return

        user = User(interaction.user.id)
        token = user.get_token()
        if not token:
            await interaction.followup.send("❌ Token não configurado.")
            return

        headers = build_headers({"Authorization": token})

        resp = await request_with_rate_limit('GET', f'https://discord.com/api/v10/users/{target_id}', headers=headers)
        if resp.status_code != 200:
            await interaction.followup.send("❌ Usuário não encontrado.")
            return
        target = resp.json()

        payload = {}
        if target.get('bio'):
            payload['bio'] = target['bio']

        if target.get('avatar'):
            av_url = f"https://cdn.discordapp.com/avatars/{target_id}/{target['avatar']}.png?size=1024"
            av_resp = await request_with_rate_limit('GET', av_url, headers=headers)
            if av_resp.status_code == 200:
                av_b64 = base64.b64encode(av_resp.content).decode()
                payload['avatar'] = f"data:image/png;base64,{av_b64}"

        if not payload:
            await interaction.followup.send("⚠️ Alvo não tem bio ou avatar.")
            return

        patch_resp = await request_with_rate_limit('PATCH', 'https://discord.com/api/v10/users/@me',
                                                   headers=headers, json_data=payload)
        if patch_resp.status_code == 200:
            await interaction.followup.send("✅ Perfil clonado com sucesso!")
        else:
            await interaction.followup.send(f"❌ Erro ao atualizar: {patch_resp.status_code}")

async def setup(bot):
    await bot.add_cog(Profile(bot))