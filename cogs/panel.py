import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import logging

logging.basicConfig(level=logging.INFO)

# --- Gerador de Silêncio Contínuo ---
class SilenceSource(discord.AudioSource):
    def read(self) -> bytes:
        # Gera 20ms de áudio totalmente em branco
        return b'\x00' * 3840
        
    def is_opus(self) -> bool:
        return False

class Panel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_channel = None

    @app_commands.command(name='painel', description='Painel de controle')
    async def painel(self, interaction: discord.Interaction):
        await interaction.response.defer()
        embed = discord.Embed(title="🛡️ Painel", color=discord.Color.blue())
        embed.add_field(name="Status", value="✅ Bot online")
        view = discord.ui.View()
        view.add_item(ButtonCall(self))
        await interaction.followup.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # O Ouvinte Implacável: Se o bot cair, ele volta
        if member.id == self.bot.user.id:
            if before.channel is not None and after.channel is None:
                if self.active_channel:
                    logging.warning("⚠️ O bot foi desconectado. Re-iniciando protocolo de voz em 2s...")
                    await asyncio.sleep(2.0)
                    try:
                        vc = await self.active_channel.connect(self_deaf=True, reconnect=True)
                        if not vc.is_playing():
                            vc.play(SilenceSource())
                        logging.info("✅ O bot voltou para a call e retomou o silêncio!")
                    except Exception as e:
                        logging.error(f"❌ Falha ao voltar: {e}")

class ButtonCall(discord.ui.Button):
    def __init__(self, cog: Panel):
        super().__init__(label="🎧 Entrar na Call (Modo Definitivo)", style=discord.ButtonStyle.success)
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("❌ Você precisa estar em um canal de voz!", ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        self.cog.active_channel = voice_channel
        msg = await interaction.followup.send(f"🔄 Conectando ao canal: {voice_channel.name}...")

        try:
            # Tenta carregar a biblioteca de codificação do Linux (se der erro, avisa no log)
            try:
                if not discord.opus.is_loaded():
                    discord.opus.load_opus('libopus.so.0')
            except Exception as e:
                logging.warning(f"⚠️ Aviso sobre Opus (pode ser ignorado se funcionar): {e}")

            voice_client = discord.utils.get(interaction.client.voice_clients, guild=interaction.guild)
            
            if voice_client and voice_client.is_connected():
                await voice_client.move_to(voice_channel)
            else:
                voice_client = await voice_channel.connect(self_deaf=True, reconnect=True)

            # Injeta o áudio silencioso e contínuo para bloquear a inatividade
            if not voice_client.is_playing():
                voice_client.play(SilenceSource())

            await msg.edit(content=f"✅ Conectado em **{voice_channel.name}**! Transmitindo pacotes e blindado.")
            
        except Exception as e:
            logging.error(f"Erro fatal ao conectar: {e}")
            await msg.edit(content=f"❌ Ocorreu um erro: {e}")

async def setup(bot):
    await bot.add_cog(Panel(bot))
