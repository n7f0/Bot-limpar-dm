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
        return {
            'token': token,
            'channel_id': row['channel_id']
        }
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
        # Cache para não recriar a mensagem toda vez
        self.message_cache = {}

    def build_embed(self, user_id: int):
        """Constrói o embed com base nas configurações atuais."""
        config = get_user_config(user_id)
        token_status = "✅ Configurado" if config['token'] else "❌ Não configurado"
        channel_status = f"✅ {config['channel_id']}" if config['channel_id'] else "❌ Não escolhido"
        
        embed = discord.Embed(
            title="**Nexzy Store Clear**",
            description="⚡ **Configuração e limpeza de mensagens em DMs**",
            color=0x2b2d31  # preto/escuro
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        
        # Status
        embed.add_field(
            name="🔑 **Token**",
            value=f"└ {token_status}",
            inline=False
        )
        embed.add_field(
            name="📌 **Canal**",
            value=f"└ {channel_status}",
            inline=False
        )
        embed.set_footer(text="Nexzy Store • v2.0", icon_url=self.bot.user.display_avatar.url)
        return embed

    # ========== COMANDO SLASH ==========
    @app_commands.command(name="paineldm", description="Exibe o painel de limpeza de DMs")
    async def paineldm(self, interaction: discord.Interaction):
        embed = self.build_embed(interaction.user.id)
        
        view = discord.ui.View(timeout=None)
        
        # Botões
        view.add_item(discord.ui.Button(
            label="🔑 Token",
            style=discord.ButtonStyle.primary,
            custom_id="setup_token"
        ))
        view.add_item(discord.ui.Button(
            label="📂 Canal",
            style=discord.ButtonStyle.secondary,
            custom_id="choose_channel"
        ))
        view.add_item(discord.ui.Button(
            label="🧹 Limpar",
            style=discord.ButtonStyle.success,
            custom_id="clear_dm"
        ))
        view.add_item(discord.ui.Button(
            label="🔍 Testar",
            style=discord.ButtonStyle.secondary,
            custom_id="test_token"
        ))
        view.add_item(discord.ui.Button(
            label="🗑️ Remover",
            style=discord.ButtonStyle.danger,
            custom_id="remove_config"
        ))
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

    # ========== HANDLER DOS BOTÕES ==========
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id")

        # ---------- BOTÃO: CONFIGURAR TOKEN ----------
        if custom_id == "setup_token":
            modal = TokenModal()
            await interaction.response.send_modal(modal)

        # ---------- BOTÃO: ESCOLHER CANAL ----------
        elif custom_id == "choose_channel":
            modal = ChannelModal()
            await interaction.response.send_modal(modal)

        # ---------- BOTÃO: LIMPAR DM ----------
        elif custom_id == "clear_dm":
            await interaction.response.defer(ephemeral=True)
            config = get_user_config(interaction.user.id)
            if not config['token']:
                await interaction.followup.send("❌ **Token não configurado.** Use o botão `🔑 Token`.", ephemeral=True)
                return
            if not config['channel_id']:
                await interaction.followup.send("❌ **Canal não escolhido.** Use o botão `📂 Canal`.", ephemeral=True)
                return

            # Confirmar
            confirm_view = ConfirmView(user_id=interaction.user.id, channel_id=config['channel_id'])
            await interaction.followup.send(
                f"⚠️ **Tem certeza?** Vou apagar mensagens no canal `{config['channel_id']}`.\nEsta ação é irreversível!",
                view=confirm_view,
                ephemeral=True
            )

        # ---------- BOTÃO: TESTAR TOKEN ----------
        elif custom_id == "test_token":
            await interaction.response.defer(ephemeral=True)
            config = get_user_config(interaction.user.id)
            if not config['token']:
                await interaction.followup.send("❌ **Nenhum token configurado.**", ephemeral=True)
                return
            
            is_valid = await test_user_token(config['token'])
            if is_valid:
                await interaction.followup.send("✅ **Token válido!** Conectado com sucesso à API do Discord.", ephemeral=True)
            else:
                await interaction.followup.send("❌ **Token inválido ou expirado.** Configure novamente.", ephemeral=True)

        # ---------- BOTÃO: REMOVER CONFIGURAÇÕES ----------
        elif custom_id == "remove_config":
            await interaction.response.defer(ephemeral=True)
            delete_user_config(interaction.user.id)
            # Atualizar o embed da mensagem original
            await self.update_embed(interaction)
            await interaction.followup.send("🗑️ **Configurações removidas com sucesso.**", ephemeral=True)

    async def update_embed(self, interaction: discord.Interaction):
        """Atualiza o embed da mensagem original do painel."""
        try:
            # Buscar a mensagem original (a que tem o painel)
            # Como não temos referência direta, procuramos pela mensagem do comando
            # Uma abordagem é armazenar o ID da mensagem, mas por simplicidade,
            # vamos editar a mensagem onde o botão foi clicado (se for uma mensagem do bot)
            message = interaction.message
            if message and message.author == self.bot.user:
                embed = self.build_embed(interaction.user.id)
                await message.edit(embed=embed)
        except Exception as e:
            logger.error(f"Erro ao atualizar embed: {e}")


# ========== MODAL PARA TOKEN ==========
class TokenModal(discord.ui.Modal, title="🔑 Configurar Token"):
    token = discord.ui.TextInput(
        label="Token da sua conta Discord",
        placeholder="Cole aqui o token (ex: ND... ou mfa...)",
        required=True,
        min_length=30,
        max_length=100,
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        token_value = self.token.value.strip()
        if not token_value.startswith(('ND', 'MT', 'MZ', 'mfa.')):
            await interaction.response.send_message("❌ **Token inválido.** Certifique-se de copiar o token correto.", ephemeral=True)
            return

        save_user_config(interaction.user.id, token=token_value)
        # Atualizar o embed da mensagem original
        cog = interaction.client.get_cog('Panel')
        if cog:
            await cog.update_embed(interaction)
        await interaction.response.send_message("✅ **Token salvo com sucesso!**", ephemeral=True)


# ========== MODAL PARA CANAL ==========
class ChannelModal(discord.ui.Modal, title="📂 Escolher Canal DM"):
    channel_id = discord.ui.TextInput(
        label="ID do canal DM",
        placeholder="Ex: 123456789012345678",
        required=True,
        min_length=17,
        max_length=20,
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            ch_id = int(self.channel_id.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ **ID inválido.** Deve ser um número.", ephemeral=True)
            return

        save_user_config(interaction.user.id, channel_id=ch_id)
        # Atualizar o embed da mensagem original
        cog = interaction.client.get_cog('Panel')
        if cog:
            await cog.update_embed(interaction)
        await interaction.response.send_message(f"✅ **Canal `{ch_id}` salvo para limpeza.**", ephemeral=True)


# ========== VIEW DE CONFIRMAÇÃO ==========
class ConfirmView(discord.ui.View):
    def __init__(self, user_id: int, channel_id: int):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.channel_id = channel_id

    @discord.ui.button(label="✅ Sim, apagar", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ **Você não pode interagir com esta confirmação.**", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        config = get_user_config(self.user_id)
        if not config['token']:
            await interaction.followup.send("❌ **Token não encontrado.**", ephemeral=True)
            return

        # Executar limpeza
        deleted, failed = await clear_dm_messages(config['token'], self.channel_id, limit=500, delay=0.8)
        if failed:
            msg = f"✅ **{deleted} mensagens apagadas.** ⚠️ {len(failed)} falhas (IDs: {', '.join(map(str, failed[:5]))}...)" if len(failed) > 5 else f"✅ **{deleted} mensagens apagadas.** ⚠️ {len(failed)} falhas."
        else:
            msg = f"✅ **{deleted} mensagens apagadas com sucesso no canal `{self.channel_id}`.**"
        await interaction.followup.send(msg, ephemeral=True)

        self.disable_all_items()
        await interaction.edit_original_response(view=self)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ **Você não pode interagir com esta confirmação.**", ephemeral=True)
            return

        await interaction.response.send_message("❌ **Operação cancelada.**", ephemeral=True)
        # Corrigido: agora usa disable_children()
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(view=self)


# ========== SETUP ==========
async def setup(bot):
    await bot.add_cog(Panel(bot))