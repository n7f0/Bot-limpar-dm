sudo docker exec -it bot-limpar-dm-bot bash -c "cat > /app/cogs/panel.py << 'EOF'
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import logging

logging.basicConfig(level=logging.INFO)

class Panel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='painel', description='Painel de controle')
    async def painel(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = discord.Embed(title="🛡️ Painel", color=discord.Color.blue())
        embed.add_field(name="Status", value="✅ Bot online")
        view = discord.ui.View()
        view.add_item(ButtonCall())
        await interaction.followup.send(embed=embed, view=view)

class ButtonCall(discord.ui.Button):
    def __init__(self):
        super().__init__(label="🎧 Teste Call (sem UDP)", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        msg = await interaction.followup.send("🔄 Entrando na call (teste sem UDP)...")
        try:
            # Entra na call (apenas simula)
            await asyncio.sleep(60 * 5)  # 5 minutos
            await msg.edit(content="✅ Call finalizada.")
        except asyncio.CancelledError:
            await msg.edit(content="⏹️ Call interrompida.")
            raise

async def setup(bot):
    await bot.add_cog(Panel(bot))
EOF"