FROM python:3.11-slim

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ARG GITHUB_TOKEN
RUN git clone https://${GITHUB_TOKEN}@github.com/n7f0/Bot-limpar-dm.git .

# 🔥 GARANTE QUE O PANEL.PY ESTÁ CORRETO (usando heredoc)
RUN cat > /app/cogs/panel.py <<'EOF'
import discord
from discord import app_commands
from discord.ext import commands
from models.user import User
from utils.logger import get_logger

logger = get_logger(__name__)

class Panel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='painel', description='Abre o painel de controle')
    async def painel(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user = User(interaction.user.id)
        embed = discord.Embed(title='🛡️ Dashboard', color=discord.Color.blue())
        tokens = user.data.get('tokens', [])
        embed.add_field(name='Tokens', value=f'{len(tokens)} configurados', inline=True)
        embed.add_field(
            name='Canal de Limpeza',
            value=f'<#{user.data.get("chat_id")}>' if user.data.get('chat_id') else 'Não definido',
            inline=False
        )
        embed.add_field(
            name='Auto-Farm',
            value='✅ Ativo' if user.data.get('auto_farming') else '❌ Inativo',
            inline=True
        )
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Panel(bot))
EOF

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]