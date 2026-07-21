import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import logging

logging.basicConfig(level=logging.INFO)

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.voice_states = True

# Removido o prefixo de texto para focar puramente em Slash Commands (/)
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

# Comando de barra com nome único para não conflitar com outros bots
@bot.tree.command(name='painelvoz', description='Painel de controle de voz do bot')
async def painelvoz(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = discord.Embed(title="🛡️ Painel de Voz", color=discord.Color.blue())
    embed.add_field(name="Status", value="✅ Bot online e blindado")
    await interaction.followup.send(embed=embed, view=PanelView())

@bot.event
async def on_ready():
    logging.info(f"✅ Bot logado com sucesso como {bot.user} (ID: {bot.user.id})")
    
    # Sincroniza o comando de barra instantaneamente em todos os servidores do bot
    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            logging.info(f"✅ Sincronizado no servidor {guild.name}: {[cmd.name for cmd in synced]}")
        except Exception as e:
            logging.error(f"❌ Erro ao sincronizar no servidor {guild.name}: {e}")

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
