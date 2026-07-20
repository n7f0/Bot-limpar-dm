FROM python:3.11-slim

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ARG GITHUB_TOKEN
RUN git clone https://${GITHUB_TOKEN}@github.com/n7f0/Bot-limpar-dm.git .

# 🔥 GARANTE QUE O PANEL.PY ESTÁ CORRETO (sobrescreve)
RUN echo 'import discord\n\
from discord import app_commands\n\
from discord.ext import commands\n\
from models.user import User\n\
from utils.logger import get_logger\n\
\n\
logger = get_logger(__name__)\n\
\n\
class Panel(commands.Cog):\n\
    def __init__(self, bot):\n\
        self.bot = bot\n\
\n\
    @app_commands.command(name="painel", description="Abre o painel de controle")\n\
    async def painel(self, interaction: discord.Interaction):\n\
        await interaction.response.defer()\n\
        user = User(interaction.user.id)\n\
        embed = discord.Embed(title="🛡️ Dashboard", color=discord.Color.blue())\n\
        tokens = user.data.get("tokens", [])\n\
        embed.add_field(name="Tokens", value=f"{len(tokens)} configurados", inline=True)\n\
        embed.add_field(name="Canal de Limpeza", value=f"<#{user.data.get("chat_id")}>" if user.data.get("chat_id") else "Não definido", inline=False)\n\
        embed.add_field(name="Auto-Farm", value="✅ Ativo" if user.data.get("auto_farming") else "❌ Inativo", inline=True)\n\
        await interaction.followup.send(embed=embed)\n\
\n\
async def setup(bot):\n\
    await bot.add_cog(Panel(bot))' > /app/cogs/panel.py

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]