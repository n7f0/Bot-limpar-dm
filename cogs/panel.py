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
        super().__init__(label="🎧 Entrar na Call", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        # Verifica se o usuário que clicou no botão está em um canal de voz
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("❌ Você precisa estar em um canal de voz para eu entrar!", ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        msg = await interaction.followup.send(f"🔄 Conectando ao canal: {voice_channel.name}...")

        try:
            # Verifica se o bot já está em alguma call neste servidor para não duplicar conexões
            voice_client = discord.utils.get(interaction.client.voice_clients, guild=interaction.guild)
            
            if voice_client and voice_client.is_connected():
                await voice_client.move_to(voice_channel)
            else:
                # Estabelece a conexão WebSocket + UDP real
                voice_client = await voice_channel.connect()

            await msg.edit(content=f"✅ Conectado na call **{voice_channel.name}** com protocolo UDP ativo.")
            
        except Exception as e:
            logging.error(f"Erro ao conectar na call: {e}")
            await msg.edit(content=f"❌ Ocorreu um erro ao tentar conectar: {e}")

async def setup(bot):
    await bot.add_cog(Panel(bot))
