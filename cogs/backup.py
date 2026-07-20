import discord
from discord import app_commands
from discord.ext import commands
import io
import asyncio
from models.user import User
from utils.helpers import build_headers, request_with_rate_limit, normal_random
from utils.logger import get_logger

logger = get_logger(__name__)

class Backup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='backup', description='Faz backup do canal configurado')
    async def backup(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user = User(interaction.user.id)
        token = user.get_token()
        if not token:
            await interaction.followup.send("❌ Token não configurado.")
            return
        chat_id = user.data.get('chat_id')
        if not chat_id:
            await interaction.followup.send("❌ Canal não definido.")
            return

        msg = await interaction.followup.send("🔄 Iniciando backup...")
        headers = build_headers({"Authorization": token})
        messages = []
        last_id = None
        limit = 1000

        while len(messages) < limit:
            url = f"https://discord.com/api/v10/channels/{chat_id}/messages?limit=100"
            if last_id:
                url += f"&before={last_id}"
            resp = await request_with_rate_limit('GET', url, headers=headers)
            if resp.status_code != 200:
                break
            data = resp.json()
            if not data:
                break
            for m in data:
                messages.append(f"[{m['timestamp']}] {m['author']['username']}: {m.get('content', '')}")
            last_id = data[-1]['id']
            await asyncio.sleep(normal_random(2, 0.5, min_val=1))

        if not messages:
            await msg.edit(content="❌ Nenhuma mensagem encontrada.")
            return

        messages.reverse()
        content = "\n".join(messages)
        buffer = io.BytesIO(content.encode('utf-8'))
        await msg.edit(content=f"✅ Backup concluído! {len(messages)} mensagens.")
        await interaction.followup.send(file=discord.File(buffer, filename="backup.txt"))

async def setup(bot):
    await bot.add_cog(Backup(bot))