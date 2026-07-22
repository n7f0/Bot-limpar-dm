import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
import sqlite3
import os
from utils.security import encrypt, decrypt, load_encryption_key
from utils.helpers import (
    stealth_clear,
    stealth_backup,
    schedule_message,
    auto_farm,
    clone_profile,
    get_user_id_from_token
)
from utils.voice_self import join_voice_call, disconnect_user_voice

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
    current_token = row['encrypted_token'] if row else None
    current_channel = row['channel_id'] if row else None
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
        self.farm_tasks = {}
        self.schedule_tasks = {}
        self.voice_tasks = {}  # user_id -> asyncio.Task

    @app_commands.command(name="paineldm", description="Abre o painel de controle")
    async def paineldm(self, interaction: discord.Interaction):
        config = get_user_config(interaction.user.id)
        embed = self._build_embed(interaction.user, config)
        view = PanelView(self, interaction.user.id, config)
        await interaction.response.send_message(embed=embed, view=view)

    def _build_embed(self, user, config):
        token_status = "✅ Configurado" if config['token'] else "❌ Não configurado"
        channel_status = f"✅ {config['channel_id']}" if config['channel_id'] else "❌ Não definido"
        embed = discord.Embed(
            title="🖤 Nexzy Store Clear",
            description="**Painel de Controle**\nSelecione uma ação no menu abaixo.",
            color=0x000000
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.add_field(name="🔑 Token", value=token_status, inline=True)
        embed.add_field(name="📌 Canal alvo", value=channel_status, inline=True)
        embed.add_field(name="📊 Status", value="🟢 Operacional", inline=True)
        embed.set_footer(text="Nexzy Store • v3.0 (Self-Bot Voice via REST)")
        embed.timestamp = discord.utils.utcnow()
        return embed

    async def start_user_voice(self, interaction: discord.Interaction, guild_id: int, channel_id: int, hours: int):
        """Inicia a conexão de voz usando o token do usuário via REST."""
        config = get_user_config(interaction.user.id)
        if not config['token']:
            await interaction.followup.send("❌ Token não configurado. Use o botão 'Configurar token'.", ephemeral=True)
            return

        if interaction.user.id in self.voice_tasks:
            await interaction.followup.send("⚠️ Você já tem uma conexão de voz ativa.", ephemeral=True)
            return

        # Cria a task assíncrona
        task = asyncio.create_task(self._voice_task(interaction, config['token'], guild_id, channel_id, hours))
        self.voice_tasks[interaction.user.id] = task
        await interaction.followup.send(f"🎧 Conectando à call por {hours}h...", ephemeral=True)

    async def _voice_task(self, interaction, token, guild_id, channel_id, hours):
        """Task que executa a conexão de voz."""
        try:
            await join_voice_call(token, guild_id, channel_id, hours, interaction.user.id)
        except Exception as e:
            logger.error(f"Erro na task de voz: {e}")
            try:
                await interaction.followup.send(f"❌ Erro na voz: {e}", ephemeral=True)
            except:
                pass
        finally:
            if interaction.user.id in self.voice_tasks:
                del self.voice_tasks[interaction.user.id]

    async def stop_user_voice(self, interaction: discord.Interaction):
        """Para a conexão de voz do usuário."""
        task = self.voice_tasks.get(interaction.user.id)
        if task:
            task.cancel()
            await disconnect_user_voice(interaction.user.id)
            del self.voice_tasks[interaction.user.id]
            await interaction.response.send_message("🔇 Desconectado da call.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nenhuma call ativa.", ephemeral=True)


class PanelView(discord.ui.View):
    def __init__(self, cog, user_id, config):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        self.config = config
        self.add_item(ActionSelect(cog, user_id, config))
        self.add_item(ConfigTokenButton(cog, user_id))
        self.add_item(ConfigChannelButton(cog, user_id))
        self.add_item(RemoveConfigButton(cog, user_id))
        self.add_item(RefreshButton(cog, user_id))


class ActionSelect(discord.ui.Select):
    def __init__(self, cog, user_id, config):
        options = [
            discord.SelectOption(label="🧹 Limpeza Furtiva", value="stealth", description="Apaga suas mensagens com delays", emoji="🧹"),
            discord.SelectOption(label="💾 Backup Stealth", value="backup", description="Salva mensagens em .txt", emoji="📁"),
            discord.SelectOption(label="⏰ Agendar Mensagem", value="schedule", description="Envia mensagem programada", emoji="📅"),
            discord.SelectOption(label="🔄 Auto-Farm", value="farm", description="Envia mensagens repetidamente", emoji="⚙️"),
            discord.SelectOption(label="🎭 Clonar Perfil", value="clone", description="Copia avatar e bio", emoji="👤"),
            discord.SelectOption(label="🎧 Entrar em Call (Self)", value="voice", description="Sua conta entra na call via REST", emoji="🔊"),
        ]
        super().__init__(placeholder="Selecione uma ação...", min_values=1, max_values=1, options=options)
        self.cog = cog
        self.user_id = user_id
        self.config = config

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Apenas o dono pode interagir.", ephemeral=True)
            return
        value = self.values[0]
        selected_label = next((opt.label for opt in self.options if opt.value == value), value)
        embed = interaction.message.embeds[0]
        embed.add_field(name="⚡ Ação selecionada", value=f"`{selected_label}`", inline=False)
        view = ActionView(self.cog, self.user_id, self.config, value)
        await interaction.response.edit_message(embed=embed, view=view)


class ActionView(discord.ui.View):
    def __init__(self, cog, user_id, config, action):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        self.config = config
        self.action = action
        if action == "stealth":
            self.add_item(StartStealthButton(cog, user_id))
        elif action == "backup":
            self.add_item(StartBackupButton(cog, user_id))
        elif action == "schedule":
            self.add_item(ScheduleButton(cog, user_id))
        elif action == "farm":
            self.add_item(StartFarmButton(cog, user_id))
            self.add_item(StopFarmButton(cog, user_id))
        elif action == "clone":
            self.add_item(CloneButton(cog, user_id))
        elif action == "voice":
            self.add_item(VoiceButton(cog, user_id))
            self.add_item(StopVoiceButton(cog, user_id))
        self.add_item(BackButton(cog, user_id))


class ConfigTokenButton(discord.ui.Button):
    def __init__(self, cog, user_id):
        super().__init__(label="🔑 Token", style=discord.ButtonStyle.primary, custom_id="config_token")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        modal = TokenModal(self.cog, self.user_id)
        await interaction.response.send_modal(modal)

class ConfigChannelButton(discord.ui.Button):
    def __init__(self, cog, user_id):
        super().__init__(label="📌 Canal", style=discord.ButtonStyle.primary, custom_id="config_channel")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        modal = ChannelModal(self.cog, self.user_id)
        await interaction.response.send_modal(modal)

class RemoveConfigButton(discord.ui.Button):
    def __init__(self, cog, user_id):
        super().__init__(label="🗑️ Remover Configs", style=discord.ButtonStyle.danger, custom_id="remove_config")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        delete_user_config(self.user_id)
        config = get_user_config(self.user_id)
        embed = self.cog._build_embed(interaction.user, config)
        view = PanelView(self.cog, self.user_id, config)
        await interaction.response.edit_message(embed=embed, view=view)

class RefreshButton(discord.ui.Button):
    def __init__(self, cog, user_id):
        super().__init__(label="🔄 Atualizar", style=discord.ButtonStyle.secondary, custom_id="refresh")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        config = get_user_config(self.user_id)
        embed = self.cog._build_embed(interaction.user, config)
        view = PanelView(self.cog, self.user_id, config)
        await interaction.response.edit_message(embed=embed, view=view)


class StartStealthButton(discord.ui.Button):
    def __init__(self, cog, user_id):
        super().__init__(label="🧹 Iniciar Limpeza", style=discord.ButtonStyle.danger, custom_id="start_stealth")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        config = get_user_config(self.user_id)
        if not config['token'] or not config['channel_id']:
            await interaction.followup.send("❌ Configure token e canal primeiro.", ephemeral=True)
            return
        view = ConfirmView(self.cog, self.user_id, "stealth", config['channel_id'])
        await interaction.followup.send("⚠️ Confirmar limpeza?", view=view, ephemeral=True)

class StartBackupButton(discord.ui.Button):
    def __init__(self, cog, user_id):
        super().__init__(label="💾 Iniciar Backup", style=discord.ButtonStyle.success, custom_id="start_backup")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        config = get_user_config(self.user_id)
        if not config['token'] or not config['channel_id']:
            await interaction.followup.send("❌ Configure token e canal.", ephemeral=True)
            return
        filename, count = await stealth_backup(config['token'], config['channel_id'], limit=3000)
        if filename:
            await interaction.followup.send(f"✅ Backup salvo ({count} mensagens).", ephemeral=True)
            await interaction.channel.send(file=discord.File(filename))
        else:
            await interaction.followup.send("❌ Falha no backup.", ephemeral=True)

class ScheduleButton(discord.ui.Button):
    def __init__(self, cog, user_id):
        super().__init__(label="⏰ Agendar Mensagem", style=discord.ButtonStyle.primary, custom_id="schedule_msg")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        modal = ScheduleModal(self.cog, self.user_id)
        await interaction.response.send_modal(modal)

class StartFarmButton(discord.ui.Button):
    def __init__(self, cog, user_id):
        super().__init__(label="🔄 Iniciar Farm", style=discord.ButtonStyle.success, custom_id="start_farm")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        modal = FarmModal(self.cog, self.user_id)
        await interaction.response.send_modal(modal)

class StopFarmButton(discord.ui.Button):
    def __init__(self, cog, user_id):
        super().__init__(label="🛑 Parar Farm", style=discord.ButtonStyle.danger, custom_id="stop_farm")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        task = self.cog.farm_tasks.get(self.user_id)
        if task:
            task.cancel()
            del self.cog.farm_tasks[self.user_id]
            await interaction.response.send_message("✅ Farm parado.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nenhum farm ativo.", ephemeral=True)

class CloneButton(discord.ui.Button):
    def __init__(self, cog, user_id):
        super().__init__(label="🎭 Clonar Perfil", style=discord.ButtonStyle.primary, custom_id="clone_profile")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        modal = CloneModal(self.cog, self.user_id)
        await interaction.response.send_modal(modal)

class VoiceButton(discord.ui.Button):
    def __init__(self, cog, user_id):
        super().__init__(label="🎧 Entrar em Call (Self)", style=discord.ButtonStyle.success, custom_id="join_voice")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        modal = VoiceModal(self.cog, self.user_id)
        await interaction.response.send_modal(modal)

class StopVoiceButton(discord.ui.Button):
    def __init__(self, cog, user_id):
        super().__init__(label="🔇 Sair da Call", style=discord.ButtonStyle.danger, custom_id="stop_voice")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        await self.cog.stop_user_voice(interaction)

class BackButton(discord.ui.Button):
    def __init__(self, cog, user_id):
        super().__init__(label="◀ Voltar", style=discord.ButtonStyle.secondary, custom_id="back")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        config = get_user_config(self.user_id)
        embed = self.cog._build_embed(interaction.user, config)
        view = PanelView(self.cog, self.user_id, config)
        await interaction.response.edit_message(embed=embed, view=view)


class TokenModal(discord.ui.Modal, title="Configurar Token"):
    token = discord.ui.TextInput(label="Token", placeholder="Cole aqui", required=True, min_length=30)

    def __init__(self, cog, user_id):
        super().__init__()
        self.cog = cog
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        save_user_config(self.user_id, token=self.token.value.strip())
        await interaction.response.send_message("✅ Token salvo!", ephemeral=True)
        config = get_user_config(self.user_id)
        embed = self.cog._build_embed(interaction.user, config)
        view = PanelView(self.cog, self.user_id, config)
        await interaction.message.edit(embed=embed, view=view)

class ChannelModal(discord.ui.Modal, title="Configurar Canal"):
    channel_id = discord.ui.TextInput(label="ID do canal", placeholder="Digite o ID", required=True, min_length=17)

    def __init__(self, cog, user_id):
        super().__init__()
        self.cog = cog
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        try:
            ch_id = int(self.channel_id.value.strip())
        except:
            await interaction.response.send_message("❌ ID inválido.", ephemeral=True)
            return
        save_user_config(self.user_id, channel_id=ch_id)
        await interaction.response.send_message("✅ Canal salvo!", ephemeral=True)
        config = get_user_config(self.user_id)
        embed = self.cog._build_embed(interaction.user, config)
        view = PanelView(self.cog, self.user_id, config)
        await interaction.message.edit(embed=embed, view=view)

class ScheduleModal(discord.ui.Modal, title="Agendar Mensagem"):
    minutes = discord.ui.TextInput(label="Minutos", placeholder="10", required=True)
    content = discord.ui.TextInput(label="Conteúdo", placeholder="Mensagem", required=True, style=discord.TextStyle.paragraph)

    def __init__(self, cog, user_id):
        super().__init__()
        self.cog = cog
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        try:
            mins = int(self.minutes.value.strip())
        except:
            await interaction.response.send_message("❌ Minutos inválido.", ephemeral=True)
            return
        config = get_user_config(self.user_id)
        if not config['token'] or not config['channel_id']:
            await interaction.response.send_message("❌ Configure token e canal.", ephemeral=True)
            return
        if self.user_id in self.cog.schedule_tasks:
            self.cog.schedule_tasks[self.user_id].cancel()
        async def wrapper():
            ok = await schedule_message(config['token'], config['channel_id'], self.content.value.strip(), mins)
            try:
                await interaction.followup.send(f"✅ Mensagem enviada!" if ok else "❌ Falha ao enviar.", ephemeral=True)
            except:
                pass
        task = asyncio.create_task(wrapper())
        self.cog.schedule_tasks[self.user_id] = task
        await interaction.response.send_message(f"⏰ Agendado para {mins} min.", ephemeral=True)

class FarmModal(discord.ui.Modal, title="Auto-Farm"):
    interval = discord.ui.TextInput(label="Intervalo (min)", placeholder="120", required=True)
    repeat = discord.ui.TextInput(label="Repetir (0 = infinito)", placeholder="0", required=True)
    messages = discord.ui.TextInput(label="Mensagens (separadas por |)", placeholder="Olá|Teste", required=True, style=discord.TextStyle.paragraph)

    def __init__(self, cog, user_id):
        super().__init__()
        self.cog = cog
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        try:
            interval = int(self.interval.value.strip())
            repeat = int(self.repeat.value.strip())
        except:
            await interaction.response.send_message("❌ Intervalo ou repetição inválidos.", ephemeral=True)
            return
        msgs = [m.strip() for m in self.messages.value.split('|') if m.strip()]
        if not msgs:
            await interaction.response.send_message("❌ Nenhuma mensagem.", ephemeral=True)
            return
        config = get_user_config(self.user_id)
        if not config['token'] or not config['channel_id']:
            await interaction.response.send_message("❌ Configure token e canal.", ephemeral=True)
            return
        if self.user_id in self.cog.farm_tasks:
            self.cog.farm_tasks[self.user_id].cancel()
        async def wrapper():
            await auto_farm(config['token'], config['channel_id'], msgs, interval_min=interval, jitter=5, repeat_count=repeat)
            if repeat > 0:
                try:
                    await interaction.followup.send(f"✅ Farm finalizado após {repeat} execuções.", ephemeral=True)
                except:
                    pass
        task = asyncio.create_task(wrapper())
        self.cog.farm_tasks[self.user_id] = task
        msg = f"🔄 Farm iniciado com {len(msgs)} mensagens a cada {interval} min."
        if repeat > 0:
            msg += f" (repetir {repeat} vezes)"
        else:
            msg += " (indefinido)"
        await interaction.response.send_message(msg, ephemeral=True)

class CloneModal(discord.ui.Modal, title="Clonar Perfil"):
    target_id = discord.ui.TextInput(label="ID do alvo", placeholder="1234567890", required=True)

    def __init__(self, cog, user_id):
        super().__init__()
        self.cog = cog
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        config = get_user_config(self.user_id)
        if not config['token']:
            await interaction.response.send_message("❌ Configure token.", ephemeral=True)
            return
        ok, msg = await clone_profile(config['token'], self.target_id.value.strip())
        await interaction.response.send_message(f"{'✅' if ok else '❌'} {msg}", ephemeral=True)

class VoiceModal(discord.ui.Modal, title="Entrar em Call (Self-Bot via REST)"):
    guild_id = discord.ui.TextInput(label="ID do servidor", placeholder="123456789", required=True)
    channel_id = discord.ui.TextInput(label="ID do canal de voz", placeholder="987654321", required=True)
    hours = discord.ui.TextInput(label="Horas", placeholder="2", required=True)

    def __init__(self, cog, user_id):
        super().__init__()
        self.cog = cog
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        try:
            gid = int(self.guild_id.value.strip())
            cid = int(self.channel_id.value.strip())
            hrs = int(self.hours.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ IDs ou horas inválidos.", ephemeral=True)
            return
        
        config = get_user_config(self.user_id)
        if not config['token']:
            await interaction.response.send_message("❌ Token não configurado. Use o botão 'Configurar token'.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.cog.start_user_voice(interaction, gid, cid, hrs)


class ConfirmView(discord.ui.View):
    def __init__(self, cog, user_id, action, channel_id):
        super().__init__(timeout=60)
        self.cog = cog
        self.user_id = user_id
        self.action = action
        self.channel_id = channel_id

    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        config = get_user_config(self.user_id)
        if not config['token']:
            await interaction.followup.send("❌ Token não encontrado.", ephemeral=True)
            return
        if self.action == "stealth":
            deleted, failed = await stealth_clear(config['token'], self.channel_id, limit=150)
            await interaction.followup.send(f"✅ Limpeza: {deleted} apagadas, {failed} falhas.", ephemeral=True)
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


async def setup(bot):
    await bot.add_cog(Panel(bot))