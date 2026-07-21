import discord
from discord.ext import commands
import os
import asyncio
import logging

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True
intents.voice_states = True

# Mantém o prefixo '!'
bot = commands.Bot(command_prefix='!', intents=intents)

# --- Gerador de Silêncio Contínuo ---
class SilenceSource(discord.AudioSource):
    def read(self) -> bytes:
        return b'\x00' * 3840
        
    def is_opus(self) -> bool:
        return False

# --- Lógica do Painel e Anti-Queda integrada ---
class PanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎧 Entrar na Call (Modo Definitivo)", style=discord.ButtonStyle.success)
    async def join_call(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("❌ Você precisa estar em um canal de voz!", ephemeral=True)
            return

        voice_channel = interaction.user.voice.channel
        msg = await interaction.followup.send(f"🔄 Conectando ao canal: {voice_channel.name}...")

        try:
            voice_client = discord.utils.get(interaction.client.voice_clients, guild=interaction.guild)
            
            if voice_client and voice_client.is_connected():
                await voice_client.move_to(voice_channel)
            else:
                voice_client = await voice_channel.connect(self_deaf=True, reconnect=True)

            if not voice_client.is_playing():
                voice_client.play(SilenceSource())

            await msg.edit(content=f"✅ Conectado em **{voice_channel.name}** com tráfego contínuo ativo!")
            
        except Exception as e:
            logging.error(f"Erro ao conectar na call: {e}")
            await msg.edit(content=f"❌ Ocorreu um erro ao tentar conectar: {e}")

# Comando alterado para '!meupainel' para evitar conflito com o outro bot
@bot.command(name='meupainel')
async def meupainel(ctx):
    embed = discord.Embed(title="🛡️ Painel", color=discord.Color.blue())
    embed.add_field(name="Status", value="✅ Bot online e blindado")
    await ctx.send(embed=embed, view=PanelView())

@bot.event
async def on_ready():
    logging.info(f"✅ Bot logado com sucesso como {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_disconnect():
    logging.warning("⚠️ Bot desconectado. Reconectando automaticamente...")

@bot.event
async def on_resumed():
    logging.info("✅ Conexão restaurada.")

if __name__ == "__main__":
    token = os.getenv('BOT_TOKEN')
    if not token:
        logging.error("❌ BOT_TOKEN não definido.")
        exit(1)

    while True:
        try:
            asyncio.run(bot.start(token))
        except discord.errors.LoginFailure as e:
            logging.error(f"❌ Falha no login: {e}. Verifique o token.")
            break
        except Exception as e:
            logging.error(f"❌ Erro fatal: {e}. Reiniciando em 10s...")
            import traceback
            traceback.print_exc()
            asyncio.sleep(10)
