import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
import sqlite3
import os
from utils.security import encrypt, decrypt, load_encryption_key
from utils.helpers import clear_dm_messages, test_user_token

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'config.db')

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_config (
            user_id INTEGER PRIMARY KEY,
            encrypted_token TEXT,
            channel_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_user_config(user_id: int, token: str = None, channel_id: int = None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT encrypted_token, channel_id FROM user_config WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    if row:
        current_token = row['encrypted_token']
        current_channel = row['channel_id']
    else:
        current_token = None
        current_channel = None
    new_token = encrypt(token) if token is not None else current_token
    new_channel = channel_id if channel_id is not None else current_channel
    cursor.execute('''
        INSERT OR REPLACE INTO user_config (user_id, encrypted_token, channel_id, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ''', (user_id, new_token, new_channel))
    conn.commit()
    conn.close()

def get_user_config(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT encrypted_token, channel_id FROM user_config WHERE user_id = ?', (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        token = decrypt(row['encrypted_token']) if row['encrypted_token'] else None
        return {'token': token, 'channel_id': row['channel_id']}
    return {'token': None, 'channel_id': None}

def delete_user_config(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM user_config WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()


class Panel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        load_encryption_key()
        init_db()

    @app_commands.command(name="paineldm", description="Exibe o painel de limpeza de DMs")
    async def paineldm(self, interaction: discord.Interaction):
        # Embed com tema escuro
        embed = discord.Embed(
            title="⚫ Nexzy Store Clear",
            description="Configuração e limpeza de mensagens em DMs",
            color=0x000000  # preto
        )
        embed.add_field(name="🔑 Token", value="✅ Configurado" if get_user_config(interaction.user.id)['token'] else "❌ Não configurado", inline=True)
        embed.add_field(name="📌 Canal", value=f"✅ {get_user_config(interaction.user.id)['channel_id']}" if get_user_config(interaction.user.id)['channel_id'] else "❌ Não escolhido", inline=True)
        embed.set_footer(text="Nexzy Store • v2.0")

        # View com Menu Select e botões
        view = discord.ui.View(timeout=None)

        # Select para ações rápidas
        select = discord.ui.Select(
            placeholder="Selecione uma ação...",
            options=[
                discord.SelectOption(label="Configurar Token", value="setup_token", emoji="🔑"),
                discord.SelectOption(label="Escolher Canal", value="choose_channel", emoji="📂"),
                discord.SelectOption(label="Limpar DM (500 msg)", value="clear_dm", emoji="🧹"),
                discord.SelectOption(label="Testar Token", value="test_token", emoji="🔍"),
                discord.SelectOption(label="Remover Configurações", value="remove_config", emoji="🗑️"),
            ]
        )
        select.callback = self.select_callback
        view.add_item(select)

        # Botões de atalho (opcional, mas manter)
        view.add_item(discord.ui.Button(label="🔑 Token", style=discord.ButtonStyle.primary, custom_id="setup_token"))
        view.add_item(discord.ui.Button(label="📂 Canal", style=discord.ButtonStyle.secondary, custom_id="choose_channel"))
        view.add_item(discord.ui.Button(label="🧹 Limpar", style=discord.ButtonStyle.success, custom_id="clear_dm"))
        view.add_item(discord.ui.Button(label="🔍 Testar", style=discord.ButtonStyle.secondary, custom_id="test_token"))
        view.add_item(discord.ui.Button(label="🗑️ Remover", style=discord.ButtonStyle.danger, custom_id="remove_config"))

        await interaction.response.send_message(embed=embed, view=view)

    async def select_callback(self, interaction: discord.Interaction):
        # Dispara a ação conforme opção selecionada
        value = interaction.data['values'][0]
        if value == "setup_token":
            modal = TokenModal()
            await interaction.response.send_modal(modal)
        elif value == "choose_channel":
            modal = ChannelModal()
            await interaction.response.send_modal(modal)
        elif value == "clear_dm":
            await self._clear_dm(interaction)
        elif value == "test_token":
            await self._test_token(interaction)
        elif value == "remove_config":
            await self._remove_config(interaction)

    # Handlers para os botões
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id")
        if custom_id == "setup_token":
            modal = TokenModal()
            await interaction.response.send_modal(modal)
        elif custom_id == "choose_channel":
            modal = ChannelModal()
            await interaction.response.send_modal(modal)
        elif custom_id == "clear_dm":
            await self._clear_dm(interaction)
        elif custom_id == "test_token":
            await self._test_token(interaction)
        elif custom_id == "remove_config":
            await self._remove_config(interaction)

    async def _clear_dm(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        config = get_user_config(interaction.user.id)
        if not config['token']:
            await interaction.followup.send("❌ Token não configurado.", ephemeral=True)
            return
        if not config['channel_id']:
            await interaction.followup.send("❌ Canal não escolhido.", ephemeral=True)
            return

        view = ConfirmView(user_id=interaction.user.id, channel_id=config['channel_id'])
        await interaction.followup.send(
            f"⚠️ Apagar mensagens no canal `{config['channel_id']}`? Esta ação é irreversível.",
            view=view,
            ephemeral=True
        )

    async def _test_token(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        config = get_user_config(interaction.user.id)
        if not config['token']:
            await interaction.followup.send("❌ Nenhum token configurado.", ephemeral=True)
            return
        is_valid = await test_user_token(config['token'])
        if is_valid:
            await interaction.followup.send("✅ Token válido!", ephemeral=True)
        else:
            await interaction.followup.send("❌ Token inválido ou expirado.", ephemeral=True)

    async def _remove_config(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        delete_user_config(interaction.user.id)
        await interaction.followup.send("🗑️ Configurações removidas.", ephemeral=True)


# ========== MODAIS ==========
class TokenModal(discord.ui.Modal, title="Configurar Token"):
    token = discord.ui.TextInput(
        label="Token da sua conta",
        placeholder="Cole aqui o token (ex: ND... ou mfa...)",
        required=True,
        min_length=30,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        token_value = self.token.value.strip()
        if not token_value.startswith(('ND', 'MT', 'MZ', 'mfa.')):
            await interaction.response.send_message("❌ Token inválido.", ephemeral=True)
            return
        save_user_config(interaction.user.id, token=token_value)
        await interaction.response.send_message("✅ Token salvo com sucesso!", ephemeral=True)

class ChannelModal(discord.ui.Modal, title="Escolher Canal DM"):
    channel_id = discord.ui.TextInput(
        label="ID do canal DM",
        placeholder="Digite o ID numérico do canal",
        required=True,
        min_length=17,
        max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            ch_id = int(self.channel_id.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ ID inválido.", ephemeral=True)
            return
        save_user_config(interaction.user.id, channel_id=ch_id)
        await interaction.response.send_message(f"✅ Canal `{ch_id}` salvo.", ephemeral=True)


# ========== VIEW DE CONFIRMAÇÃO ==========
class ConfirmView(discord.ui.View):
    def __init__(self, user_id: int, channel_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.channel_id = channel_id

    @discord.ui.button(label="✅ Sim, apagar", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        config = get_user_config(self.user_id)
        if not config['token']:
            await interaction.followup.send("❌ Token não encontrado.", ephemeral=True)
            return

        deleted = await clear_dm_messages(config['token'], self.channel_id, limit=500, delay=0.8)
        await interaction.followup.send(f"✅ {deleted} mensagens apagadas.", ephemeral=True)

        # Desabilitar botões após a ação
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(view=self)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return

        await interaction.response.send_message("❌ Cancelado.", ephemeral=True)
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(view=self)


# ========== SETUP ==========
async def setup(bot):
    await bot.add_cog(Panel(bot))