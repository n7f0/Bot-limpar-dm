import discord
from discord import app_commands
from discord.ext import commands
from utils.db import get_connection
from utils.logger import get_logger

logger = get_logger(__name__)

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='stats', description='Mostra estatísticas do bot')
    async def stats(self, interaction: discord.Interaction):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM scheduled_tasks WHERE active = 1")
        total_tasks = cursor.fetchone()[0]
        conn.close()

        embed = discord.Embed(title="📊 Estatísticas", color=discord.Color.green())
        embed.add_field(name="Usuários", value=total_users, inline=True)
        embed.add_field(name="Tarefas agendadas", value=total_tasks, inline=True)
        embed.add_field(name="Cogs carregados", value=len(self.bot.cogs), inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='reload_cog', description='Recarrega um cog (admin)')
    @app_commands.describe(cog='Nome do cog (ex: clean)')
    async def reload_cog(self, interaction: discord.Interaction, cog: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Apenas administradores.", ephemeral=True)
            return
        try:
            await self.bot.reload_extension(f"cogs.{cog}")
            await interaction.response.send_message(f"✅ Cog `{cog}` recarregado.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erro: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Admin(bot))