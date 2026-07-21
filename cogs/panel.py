import discord
from discord.ext import commands
from discord import app_commands
import logging
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

    # ========== COMANDO SLASH: PAINEL ==========
    @app_commands.command(name="paineldm", description="🧹 Painel de limpeza de DMs - Nexzy Store")
    async def paineldm(self, interaction: discord.Interaction):
        """Exibe o painel principal com menu seletor."""
        embed = discord.Embed(
            title="🛡️ Nexzy Store Clear",
            description="Gerencie suas DMs com segurança e praticidade.",
            color=0x6c5ce7  # roxo escuro
        )
        embed.add_field(
            name="📋 Menu de ações",
            value=(
                "**Selecione uma opção abaixo:**\n\n"
                "🔑 **Configurar Token** – Salve seu token de usuário\n"
                "📂 **Escolher Canal** – Defina o canal DM alvo\n"
                "🧹 **Limpar DM** – Apague mensagens (até 500)\n"
                "🔍 **Testar Token** – Verifique se o token é válido\n"
                "🗑️ **Remover Configurações** – Limpe seus dados"
            ),
            inline=False
        )
        embed.set_footer(text="Nexzy Store Clear • v2.0")

        # View com menu seletor (dropdown)
        view = discord.ui.View(timeout=None)

        # Dropdown seletor de ações
        select = discord.ui.Select(
            placeholder="📌 Escolha uma ação...",
            options=[
                discord.SelectOption(label="🔑 Configurar Token", value="setup_token", description="Salve seu token de usuário", emoji="🔑"),
                discord.SelectOption(label="📂 Escolher Canal", value="choose_channel", description="Defina o canal DM alvo", emoji="📂"),
                discord.SelectOption(label="🧹 Limpar DM", value="clear_dm", description="Apague mensagens na DM configurada", emoji="🧹"),
                discord.SelectOption(label="🔍 Testar Token", value="test_token", description="Verifique se o token é válido", emoji="🔍"),
                discord.SelectOption(label="🗑️ Remover Configurações", value="remove_config", description="Apague token e canal salvos", emoji="🗑️"),
            ],
            custom_id="action_menu"
        )
        view.add_item(select)

        # Botão de recarregar painel (opcional)
        reload_btn = discord.ui.Button(
            label="🔄 Recarregar",
            style=discord.ButtonStyle.secondary,
            custom_id="reload_panel"
        )
        view.add_item(reload_btn)

        # Mostrar status atual
        config = get_user_config(interaction.user.id)
        status_msg = (
            f"🔑 Token: {'✅ Configurado' if config['token'] else '❌ Não configurado'}\n"
            f"📌 Canal: {f'✅ {config["channel_id"]}' if config['channel_id'] else '❌ Não escolhido'}"
        )
        embed.add_field(name="📊 Status atual", value=status_msg, inline=False)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

    # ========== HANDLER DE INTERAÇÕES ==========
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.component:
            custom_id = interaction.data.get("custom_id")

            # ---------- MENU DROPDOWN ----------
            if custom_id == "action_menu":
                selected = interaction.data.get("values", [None])[0]
                if selected == "setup_token":
                    await interaction.response.send_modal(TokenModal())
                elif selected == "choose_channel":
                    await interaction.response.send_modal(ChannelModal())
                elif selected == "clear_dm":
                    await self.handle_clear_dm(interaction)
                elif selected == "test_token":
                    await self.handle_test_token(interaction)
                elif selected == "remove_config":
                    await self.handle_remove_config(interaction)

            # ---------- BOTÃO RECARREGAR ----------
            elif custom_id == "reload_panel":
                await interaction.response.defer(ephemeral=True)
                # Reenviar o painel atualizado
                await interaction.delete_original_response()
                await self.paineldm(interaction)

    # ========== FUNÇÕES AUXILIARES ==========
    async def handle_clear_dm(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        config = get_user_config(interaction.user.id)
        if not config['token']:
            await interaction.followup.send("❌ Você não configurou seu token. Use o menu 'Configurar Token'.", ephemeral=True)
            return
        if not config['channel_id']:
            await interaction.followup.send("❌ Você não escolheu um canal. Use o menu 'Escolher Canal'.", ephemeral=True)
            return

        # View de confirmação com opção de quantidade
        confirm_view = ConfirmView(user_id=interaction.user.id, channel_id=config['channel_id'])
        await interaction.followup.send(
            f"⚠️ Tem certeza que deseja apagar **até 500 mensagens** no canal `{config['channel_id']}`?\n"
            "Esta ação é irreversível.",
            view=confirm_view,
            ephemeral=True
        )

    async def handle_test_token(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        config = get_user_config(interaction.user.id)
        if not config['token']:
            await interaction.followup.send("❌ Nenhum token configurado.", ephemeral=True)
            return
        is_valid = await test_user_token(config['token'])
        if is_valid:
            await interaction.followup.send("✅ Token válido! Conexão com a API do Discord bem-sucedida.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Token inválido ou expirado. Reconfigure.", ephemeral=True)

    async def handle_remove_config(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        delete_user_config(interaction.user.id)
        await interaction.followup.send("🗑️ Todas as configurações (token e canal) foram removidas.", ephemeral=True)


# ========== MODAL PARA TOKEN ==========
class TokenModal(discord.ui.Modal, title="🔑 Configurar Token"):
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
            await interaction.response.send_message("❌ Token inválido. Certifique-se de copiar o token correto.", ephemeral=True)
            return
        save_user_config(interaction.user.id, token=token_value)
        await interaction.response.send_message("✅ Token salvo com sucesso!", ephemeral=True)


# ========== MODAL PARA CANAL ==========
class ChannelModal(discord.ui.Modal, title="📂 Escolher Canal DM"):
    channel_id = discord.ui.TextInput(
        label="ID do canal DM",
        placeholder="Digite o ID numérico do canal (ex: 123456789012345678)",
        required=True,
        min_length=17,
        max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            ch_id = int(self.channel_id.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ ID inválido. Deve ser um número.", ephemeral=True)
            return
        save_user_config(interaction.user.id, channel_id=ch_id)
        await interaction.response.send_message(f"✅ Canal `{ch_id}` salvo para limpeza.", ephemeral=True)


# ========== VIEW DE CONFIRMAÇÃO ==========
class ConfirmView(discord.ui.View):
    def __init__(self, user_id: int, channel_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.channel_id = channel_id

    @discord.ui.button(label="✅ Sim, apagar", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Você não pode interagir com esta confirmação.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        config = get_user_config(self.user_id)
        if not config['token']:
            await interaction.followup.send("❌ Token não encontrado.", ephemeral=True)
            return
        # Limpar até 500 mensagens (ajustável)
        deleted = await clear_dm_messages(config['token'], self.channel_id, limit=500, delay=0.8)
        await interaction.followup.send(f"✅ {deleted} mensagens apagadas no canal `{self.channel_id}`.", ephemeral=True)
        self.disable_all_items()
        await interaction.edit_original_response(view=self)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Você não pode interagir com esta confirmação.", ephemeral=True)
            return
        await interaction.response.send_message("❌ Operação cancelada.", ephemeral=True)
        self.disable_all_items()
        await interaction.edit_original_response(view=self)


# ========== SETUP ==========
async def setup(bot):
    await bot.add_cog(Panel(bot))