import discord
from discord import app_commands
from discord.ext import commands
import logging

logging.basicConfig(level=logging.INFO)

# --- Gerador de Silêncio Contínuo ---
# Engana o Discord transmitindo áudio vazio (evita timeout por inatividade)
class SilenceSource(discord.AudioSource):
    def read(self) -> bytes:
        # Retorna 3840 bytes de zeros (equivalente a 20ms de áudio PCM em branco)
        return b'\x00' * 3840
        
    def is_opus(self) -> bool:
        return False

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
        super().__init__(label="🎧 Entrar na Call (Estável)", style=discord.ButtonStyle.success)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("❌ Você precisa estar em um canal de voz!", ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        msg = await interaction.followup.send(f"🔄 Conectando ao canal: {voice_channel.name}...")

        try:
            voice_client = discord.utils.get(interaction.client.voice_clients, guild=interaction.guild)
            
            # Conecta ou move o bot
            if voice_client and voice_client.is_connected():
                await voice_client.move_to(voice_channel)
            else:
                voice_client = await voice_channel.connect()

            # --- O Segredo está aqui ---
            # Se o bot não estiver tocando nada, inicia a transmissão infinita de silêncio
            if not voice_client.is_playing():
                voice_client.play(SilenceSource())

            await msg.edit(content=f"✅ Conectado na call **{voice_channel.name}**. Transmitindo silêncio para evitar desconexão.")
            
        except Exception as e:
            logging.error(f"Erro ao conectar na call: {e}")
            await msg.edit(content=f"❌ Ocorreu um erro ao tentar conectar: {e}")

async def setup(bot):
    await bot.add_cog(Panel(bot))
