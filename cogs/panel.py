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
        embed = discord.Embed(
            title="🛡️ Dashboard",
            color=discord.Color.blue()
        )
        tokens = user.data.get('tokens', [])
        embed.add_field(name="Tokens", value=f"{len(tokens)} configurados", inline=True)
        embed.add_field(
            name="Canal de Limpeza",
            value=f"<#{user.data.get('chat_id')}>" if user.data.get('chat_id') else "Não definido",
            inline=False
        )
        embed.add_field(
            name="Auto-Farm",
            value="✅ Ativo" if user.data.get('auto_farming') else "❌ Inativo",
            inline=True
        )
        await interaction.followup.send(embed=embed)

# ⚠️ FUNÇÃO OBRIGATÓRIA PARA COGS
async def setup(bot):
    await bot.add_cog(Panel(bot))