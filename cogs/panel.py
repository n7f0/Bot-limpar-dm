import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio
import sqlite3
import os
import random
from utils.security import encrypt, decrypt, load_encryption_key
from utils.helpers import (
    stealth_clear,
    stealth_backup,
    schedule_message,
    auto_farm,
    clone_profile,
    get_user_id_from_token
)

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
        self.panel_messages = {}  # user_id -> message_id
        self.farm_tasks = {}      # user_id -> asyncio.Task
        self.schedule_tasks = {}  # user_id -> asyncio.Task
        self.voice_connections = {}  # guild_id -> voice_client

    # ========== COMANDO /paineldm ==========
    @app_commands.command(name="paineldm", description="Abre o painel de controle Nexzy Store Clear")
    async def paineldm(self, interaction: discord.Interaction):
        config = get_user_config(interaction.user.id)
        embed = self._build_embed(interaction.user, config)

        view = PanelView(self, interaction.user.id, config)
        await interaction.response.send_message(embed=embed, view=view)
        # Guarda a mensagem para edições futuras
        msg = await interaction.original_response()
        self.panel_messages[interaction.user.id] = msg.id

    def _build_embed(self, user, config):
        token_status = "✅ Configurado" if config['token'] else "❌ Não configurado"
        channel_status = f"✅ {config['channel_id']}" if config['channel_id'] else "❌ Não definido"

        embed = discord.Embed(
            title="🖤 Nexzy Store Clear",
            description="**Painel de Controle Avançado**\nSelecione uma ação no menu abaixo.",
            color=0x000000  # preto
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.add_field(name="🔑 Token", value=token_status, inline=True)
        embed.add_field(name="📌 Canal alvo", value=channel_status, inline=True)
        embed.add_field(name="📊 Status", value="🟢 Operacional", inline=True)
        embed.set_footer(text="Nexzy Store • v2.0 | Selecione a ação no menu")
        embed.timestamp = discord.utils.utcnow()
        return embed


# ========== VIEW DO PAINEL COM SELECT MENU ==========
class PanelView(discord.ui.View):
    def __init__(self, cog, user_id, config):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        self.config = config

        # Select menu para escolher a ação
        self.add_item(ActionSelect(cog, user_id, config))

        # Botões de configuração (sempre visíveis)
        self.add_item(ConfigTokenButton(cog, user_id))
        self.add_item(ConfigChannelButton(cog, user_id))
        self.add_item(RemoveConfigButton(cog, user_id))

        # Botão de atualizar status (reload)
        self.add_item(RefreshButton(cog, user_id))


# ========== SELECT MENU ==========
class ActionSelect(discord.ui.Select):
    def __init__(self, cog, user_id, config):
        options = [
            discord.SelectOption(label="🔹 Limpeza Furtiva", value="stealth", description="Apaga suas mensagens com delays aleatórios", emoji="🧹"),
            discord.SelectOption(label="💾 Backup Stealth", value="backup", description="Salva mensagens do chat em .txt", emoji="📁"),
            discord.SelectOption(label="⏰ Agendar Mensagem", value="schedule", description="Envia mensagem programada", emoji="📅"),
            discord.SelectOption(label="🔄 Auto-Farm", value="farm", description="Envia mensagens repetidamente", emoji="⚙️"),
            discord.SelectOption(label="🎭 Clonar Perfil", value="clone", description="Copia avatar e bio de outro usuário", emoji="👤"),
            discord.SelectOption(label="🎧 Entrar em Call", value="voice", description="Conecta-se a canal de voz", emoji="🔊"),
        ]
        super().__init__(placeholder="Selecione uma ação...", min_values=1, max_values=1, options=options)
        self.cog = cog
        self.user_id = user_id
        self.config = config

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Você não pode interagir com este painel.", ephemeral=True)
            return

        value = self.values[0]
        # Atualizar o embed para mostrar a ação selecionada
        embed = interaction.message.embeds[0]
        embed.add_field(name="⚡ Ação selecionada", value=f"`{self.options[0].label}`", inline=False)

        # Criar uma nova view com os botões específicos da ação
        view = ActionView(self.cog, self.user_id, self.config, value)
        await interaction.response.edit_message(embed=embed, view=view)


# ========== VIEW DE AÇÃO (botões específicos) ==========
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

        # Botão voltar ao menu principal
        self.add_item(BackButton(cog, user_id))

# ========== BOTÕES DE CONFIGURAÇÃO ==========
class ConfigTokenButton(discord.ui.Button):
    def __init__(self, cog, user_id):
        super().__init__(label="🔑 Token", style=discord.ButtonStyle.primary, custom_id="config_token")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Apenas o dono pode configurar.", ephemeral=True)
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
            await interaction.response.send_message("❌ Apenas o dono pode configurar.", ephemeral=True)
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
            await interaction.response.send_message("❌ Apenas o dono pode remover.", ephemeral=True)
            return
        delete_user_config(self.user_id)
        # Atualizar painel
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
            await interaction.response.send_message("❌ Apenas o dono pode atualizar.", ephemeral=True)
            return
        config = get_user_config(self.user_id)
        embed = self.cog._build_embed(interaction.user, config)
        view = PanelView(self.cog, self.user_id, config)
        await interaction.response.edit_message(embed=embed, view=view)


# ========== BOTÕES DE AÇÃO ==========
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

        # Confirmação
        view = ConfirmView(self.cog, self.user_id, "stealth", config['channel_id'])
        await interaction.followup.send("⚠️ Isso apagará suas mensagens no canal. Confirmar?", view=view, ephemeral=True)

class StartBackupButton(discord.ui.Button):
    def __init__(self, cog, user_id):
        super().__init__(label="💾 Iniciar Backup", style=discord.ButtonStyle.success, custom_id="start_backup")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        config = get_user_config(self.user_id)
        if not config['token'] or not config['channel_id']:
            await interaction.followup.send("❌ Configure token e canal primeiro.", ephemeral=True)
            return

        # Executar backup
        filename, count = await stealth_backup(config['token'], config['channel_id'], limit=3000)
        if filename:
            await interaction.followup.send(f"✅ Backup concluído! {count} mensagens salvas.", ephemeral=True)
            # Enviar o arquivo no mesmo canal do painel (público)
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
            await interaction.response.send_message("❌ Apenas o dono pode agendar.", ephemeral=True)
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
            await interaction.response.send_message("❌ Apenas o dono pode iniciar farm.", ephemeral=True)
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
            await interaction.response.send_message("❌ Apenas o dono pode parar.", ephemeral=True)
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
            await interaction.response.send_message("❌ Apenas o dono pode clonar.", ephemeral=True)
            return
        modal = CloneModal(self.cog, self.user_id)
        await interaction.response.send_modal(modal)

class VoiceButton(discord.ui.Button):
    def __init__(self, cog, user_id):
        super().__init__(label="🎧 Entrar em Call", style=discord.ButtonStyle.primary, custom_id="join_voice")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Apenas o dono pode conectar.", ephemeral=True)
            return
        modal = VoiceModal(self.cog, self.user_id)
        await interaction.response.send_modal(modal)

class BackButton(discord.ui.Button):
    def __init__(self, cog, user_id):
        super().__init__(label="◀ Voltar", style=discord.ButtonStyle.secondary, custom_id="back")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Apenas o dono pode voltar.", ephemeral=True)
            return
        config = get_user_config(self.user_id)
        embed = self.cog._build_embed(interaction.user, config)
        view = PanelView(self.cog, self.user_id, config)
        await interaction.response.edit_message(embed=embed, view=view)


# ========== MODAIS ==========
class TokenModal(discord.ui.Modal, title="Configurar Token"):
    token = discord.ui.TextInput(label="Token da conta", placeholder="Cole aqui", required=True, min_length=30)

    def __init__(self, cog, user_id):
        super().__init__()
        self.cog = cog
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Apenas o dono pode configurar.", ephemeral=True)
            return
        save_user_config(self.user_id, token=self.token.value.strip())
        await interaction.response.send_message("✅ Token salvo!", ephemeral=True)
        # Atualizar painel
        config = get_user_config(self.user_id)
        embed = self.cog._build_embed(interaction.user, config)
        view = PanelView(self.cog, self.user_id, config)
        msg_id = self.cog.panel_messages.get(self.user_id)
        if msg_id:
            channel = interaction.channel
            try:
                msg = await channel.fetch_message(msg_id)
                await msg.edit(embed=embed, view=view)
            except:
                pass

class ChannelModal(discord.ui.Modal, title="Configurar Canal"):
    channel_id = discord.ui.TextInput(label="ID do canal DM", placeholder="Digite o ID", required=True, min_length=17)

    def __init__(self, cog, user_id):
        super().__init__()
        self.cog = cog
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Apenas o dono pode configurar.", ephemeral=True)
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
        msg_id = self.cog.panel_messages.get(self.user_id)
        if msg_id:
            channel = interaction.channel
            try:
                msg = await channel.fetch_message(msg_id)
                await msg.edit(embed=embed, view=view)
            except:
                pass

class ScheduleModal(discord.ui.Modal, title="Agendar Mensagem"):
    minutes = discord.ui.TextInput(label="Minutos", placeholder="10", required=True)
    content = discord.ui.TextInput(label="Conteúdo", placeholder="Mensagem programada", required=True, style=discord.TextStyle.paragraph)

    def __init__(self, cog, user_id):
        super().__init__()
        self.cog = cog
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Apenas o dono pode agendar.", ephemeral=True)
            return
        try:
            mins = int(self.minutes.value.strip())
        except:
            await interaction.response.send_message("❌ Minutos inválido.", ephemeral=True)
            return
        config = get_user_config(self.user_id)
        if not config['token'] or not config['channel_id']:
            await interaction.response.send_message("❌ Configure token e canal primeiro.", ephemeral=True)
            return

        # Cancelar agendamento anterior
        if self.user_id in self.cog.schedule_tasks:
            self.cog.schedule_tasks[self.user_id].cancel()

        # Criar task
        async def schedule_wrapper():
            success = await schedule_message(config['token'], config['channel_id'], self.content.value.strip(), mins)
            if success:
                await interaction.followup.send(f"✅ Mensagem enviada após {mins} min.", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Falha ao enviar mensagem agendada.", ephemeral=True)

        task = asyncio.create_task(schedule_wrapper())
        self.cog.schedule_tasks[self.user_id] = task
        await interaction.response.send_message(f"⏰ Mensagem agendada para daqui a {mins} minutos.", ephemeral=True)

class FarmModal(discord.ui.Modal, title="Configurar Auto-Farm"):
    interval = discord.ui.TextInput(label="Intervalo (minutos)", placeholder="120", required=True)
    messages = discord.ui.TextInput(label="Mensagens (separadas por |)", placeholder="Olá|Teste", required=True, style=discord.TextStyle.paragraph)

    def __init__(self, cog, user_id):
        super().__init__()
        self.cog = cog
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Apenas o dono pode iniciar farm.", ephemeral=True)
            return
        try:
            interval = int(self.interval.value.strip())
        except:
            await interaction.response.send_message("❌ Intervalo inválido.", ephemeral=True)
            return
        msgs = [m.strip() for m in self.messages.value.split('|') if m.strip()]
        if not msgs:
            await interaction.response.send_message("❌ Nenhuma mensagem válida.", ephemeral=True)
            return
        config = get_user_config(self.user_id)
        if not config['token'] or not config['channel_id']:
            await interaction.response.send_message("❌ Configure token e canal primeiro.", ephemeral=True)
            return

        # Cancelar farm anterior
        if self.user_id in self.cog.farm_tasks:
            self.cog.farm_tasks[self.user_id].cancel()

        # Iniciar farm
        async def farm_wrapper():
            await auto_farm(config['token'], config['channel_id'], msgs, interval_min=interval, jitter=5)
        task = asyncio.create_task(farm_wrapper())
        self.cog.farm_tasks[self.user_id] = task
        await interaction.response.send_message(f"🔄 Farm iniciado com {len(msgs)} mensagens a cada {interval} min.", ephemeral=True)

class CloneModal(discord.ui.Modal, title="Clonar Perfil"):
    target_id = discord.ui.TextInput(label="ID do usuário alvo", placeholder="1234567890", required=True)

    def __init__(self, cog, user_id):
        super().__init__()
        self.cog = cog
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Apenas o dono pode clonar.", ephemeral=True)
            return
        config = get_user_config(self.user_id)
        if not config['token']:
            await interaction.response.send_message("❌ Configure token primeiro.", ephemeral=True)
            return
        target = self.target_id.value.strip()
        ok, msg = await clone_profile(config['token'], target)
        await interaction.response.send_message(f"{'✅' if ok else '❌'} {msg}", ephemeral=True)

class VoiceModal(discord.ui.Modal, title="Entrar em Call"):
    guild_id = discord.ui.TextInput(label="ID do servidor", placeholder="123456789", required=True)
    channel_id = discord.ui.TextInput(label="ID do canal de voz", placeholder="987654321", required=True)
    hours = discord.ui.TextInput(label="Horas", placeholder="2", required=True)

    def __init__(self, cog, user_id):
        super().__init__()
        self.cog = cog
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Apenas o dono pode conectar.", ephemeral=True)
            return
        try:
            guild_id = int(self.guild_id.value.strip())
            channel_id = int(self.channel_id.value.strip())
            hours = int(self.hours.value.strip())
        except:
            await interaction.response.send_message("❌ IDs ou horas inválidos.", ephemeral=True)
            return

        # Conectar usando o bot
        guild = self.cog.bot.get_guild(guild_id)
        if not guild:
            await interaction.response.send_message("❌ Servidor não encontrado.", ephemeral=True)
            return
        channel = guild.get_channel(channel_id)
        if not channel or not isinstance(channel, discord.VoiceChannel):
            await interaction.response.send_message("❌ Canal de voz não encontrado.", ephemeral=True)
            return

        # Verificar se já está conectado
        if guild.voice_client:
            await interaction.response.send_message("❌ Já estou conectado a um canal de voz neste servidor.", ephemeral=True)
            return

        try:
            vc = await channel.connect()
            self.cog.voice_connections[guild_id] = vc
            await interaction.response.send_message(f"🎧 Conectado ao canal {channel.name} por {hours}h.", ephemeral=True)

            # Manter conexão por X horas enviando silêncio
            # Para simular áudio real, enviaremos um sinal de silêncio usando FFmpeg se disponível
            # Senão, apenas manteremos a conexão viva.
            try:
                # Tenta enviar um arquivo de áudio de silêncio se FFmpeg estiver instalado
                silence_file = '/app/silence.mp3'
                if not os.path.exists(silence_file):
                    # Cria um arquivo de silêncio de 1s (se não existir)
                    import subprocess
                    subprocess.run(['ffmpeg', '-f', 'lavfi', '-i', 'anullsrc=r=44100:cl=mono', '-t', '1', '-acodec', 'libmp3lame', silence_file], check=False)
                
                # Reproduz silêncio em loop durante as horas
                # Como não queremos sair do loop, usamos um loop que toca silêncio a cada 30s
                start_time = time.time()
                while time.time() - start_time < hours * 3600:
                    # O Discord desconecta automaticamente se não receber áudio por ~5min
                    # Então enviamos um sinal de áudio vazio (silêncio) a cada 30s
                    if os.path.exists(silence_file):
                        vc.play(discord.FFmpegPCMAudio(silence_file), after=lambda e: None)
                        await asyncio.sleep(30)
                    else:
                        # Fallback: apenas aguarda e reenvia um sinal de atividade
                        await asyncio.sleep(60)
            except Exception as e:
                # Se não tiver FFmpeg, apenas espera
                logger.warning(f"Reprodução de silêncio falhou: {e}. Apenas mantendo conexão viva.")
                await asyncio.sleep(hours * 3600)

            await vc.disconnect()
            await interaction.followup.send("🔇 Desconectado após o tempo programado.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erro ao conectar: {e}", ephemeral=True)
            logger.error(f"Erro ao conectar ao canal de voz: {e}")


# ========== VIEW DE CONFIRMAÇÃO ==========
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
            await interaction.followup.send(f"✅ Limpeza concluída: {deleted} apagadas, {failed} falhas.", ephemeral=True)

        # Desabilitar botões
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(view=self)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        await interaction.response.send_message("❌ Operação cancelada.", ephemeral=True)
        for child in self.children:
            child.disabled = True
        await interaction.edit_original_response(view=self)


# ========== SETUP DA COG ==========
async def setup(bot):
    await bot.add_cog(Panel(bot))