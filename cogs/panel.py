import discord
from discord.ext import commands
from discord import app_commands
import json
from utils.db import get_user_data, save_user_data
from utils.security import encrypt, decrypt
from utils.task_manager import task_mgr
from utils.helpers import get_user_id_from_token, stealth_clear, auto_farm
from utils.voice_ws import start_voice_task

class Panel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="paineldm", description="Abre o painel V4")
    async def paineldm(self, interaction: discord.Interaction):
        config = get_user_data(interaction.user.id)
        embed = self._build_embed(interaction.user, config)
        view = PanelView(self, interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

    def _build_embed(self, user, config):
        tokens = config.get('tokens', [])
        idx = config.get('active_token_index', 0)
        
        token_status = "✅ Configurado" if tokens and idx < len(tokens) else "❌ Nenhum"
        account_count = f"({len(tokens)} contas)"
        ch = config.get('channel_id')
        
        embed = discord.Embed(
            title="🖤 Nexzy Store - Painel V4",
            description="**Sistema Avançado com Multi-Contas & Analytics**\nSelecione uma ação no menu abaixo.",
            color=0x2b2d31
        )
        embed.add_field(name="🔑 Token Ativo", value=f"{token_status} {account_count}", inline=True)
        embed.add_field(name="📌 Canal Alvo", value=f"ID: {ch}" if ch else "❌ Não definido", inline=True)
        
        stats = f"🧹 Apagadas: {config.get('stats_cleared', 0)}\n🔄 Farmadas: {config.get('stats_farmed', 0)}"
        embed.add_field(name="📊 Suas Estatísticas", value=stats, inline=False)
        
        active_tasks = []
        if task_mgr.is_running(user.id, "stealth"): active_tasks.append("🧹 Limpeza")
        if task_mgr.is_running(user.id, "farm"): active_tasks.append("🔄 Farm")
        if task_mgr.is_running(user.id, "voice"): active_tasks.append("🔊 Voz")
        
        status_str = ", ".join(active_tasks) if active_tasks else "Nenhuma tarefa ativa."
        embed.add_field(name="⚙️ Tarefas em Execução", value=f"```\n{status_str}\n```", inline=False)
        
        return embed

class PanelView(discord.ui.View):
    def __init__(self, cog, user_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        
        options = [
            discord.SelectOption(label="🧹 Controlar Limpeza", value="stealth"),
            discord.SelectOption(label="🔄 Controlar Farm", value="farm"),
            discord.SelectOption(label="🔊 Controlar Call (Self)", value="voice"),
            discord.SelectOption(label="⚙️ Configurações (Tokens, Canal, Webhook)", value="config"),
        ]
        
        self.select = discord.ui.Select(placeholder="Selecione um módulo...", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)
        
        btn = discord.ui.Button(label="🔄 Atualizar Painel", style=discord.ButtonStyle.secondary)
        btn.callback = self.refresh_callback
        self.add_item(btn)

    async def select_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        
        val = self.select.values[0]
        config = get_user_data(self.user_id)
        embed = self.cog._build_embed(interaction.user, config)
        
        view = ControlView(self.cog, self.user_id, val)
        await interaction.response.edit_message(embed=embed, view=view)

    async def refresh_callback(self, interaction: discord.Interaction):
        config = get_user_data(self.user_id)
        embed = self.cog._build_embed(interaction.user, config)
        await interaction.response.edit_message(embed=embed, view=self)

class ControlView(discord.ui.View):
    def __init__(self, cog, user_id, module):
        super().__init__(timeout=None)
        self.cog = cog
        self.user_id = user_id
        self.module = module
        
        config = get_user_data(user_id)
        
        if module == "stealth":
            btn_start = discord.ui.Button(label="Iniciar Limpeza", style=discord.ButtonStyle.success)
            btn_stop = discord.ui.Button(label="Parar Limpeza", style=discord.ButtonStyle.danger)
            btn_start.callback = self.start_stealth
            btn_stop.callback = self.stop_stealth
            self.add_item(btn_start)
            self.add_item(btn_stop)
            
        elif module == "farm":
            btn_start = discord.ui.Button(label="Iniciar Farm", style=discord.ButtonStyle.success)
            btn_stop = discord.ui.Button(label="Parar Farm", style=discord.ButtonStyle.danger)
            btn_start.callback = self.start_farm
            btn_stop.callback = self.stop_farm
            self.add_item(btn_start)
            self.add_item(btn_stop)

        elif module == "voice":
            btn_start = discord.ui.Button(label="Entrar na Call", style=discord.ButtonStyle.success)
            btn_stop = discord.ui.Button(label="Sair da Call", style=discord.ButtonStyle.danger)
            btn_start.callback = self.start_voice
            btn_stop.callback = self.stop_voice
            self.add_item(btn_start)
            self.add_item(btn_stop)
            
        elif module == "config":
            btn_token = discord.ui.Button(label="Add Token", style=discord.ButtonStyle.primary)
            btn_ch = discord.ui.Button(label="Set Canal", style=discord.ButtonStyle.primary)
            btn_hook = discord.ui.Button(label="Set Webhook", style=discord.ButtonStyle.primary)
            
            btn_token.callback = self.add_token
            btn_ch.callback = self.set_channel
            btn_hook.callback = self.set_webhook
            
            self.add_item(btn_token)
            self.add_item(btn_ch)
            self.add_item(btn_hook)

        btn_back = discord.ui.Button(label="◀ Voltar", style=discord.ButtonStyle.secondary)
        btn_back.callback = self.back
        self.add_item(btn_back)

    async def get_active_token(self):
        config = get_user_data(self.user_id)
        tokens = config.get('tokens', [])
        idx = config.get('active_token_index', 0)
        if tokens and idx < len(tokens):
            return decrypt(tokens[idx])
        return None

    async def start_stealth(self, interaction: discord.Interaction):
        token = await self.get_active_token()
        config = get_user_data(self.user_id)
        if not token or not config.get('channel_id'):
            return await interaction.response.send_message("❌ Token ou Canal não configurados.", ephemeral=True)
            
        if task_mgr.is_running(self.user_id, "stealth"):
            return await interaction.response.send_message("⚠️ Limpeza já está em andamento.", ephemeral=True)
            
        coro = stealth_clear(token, config['channel_id'], self.user_id)
        task_mgr.add_task(self.user_id, "stealth", coro)
        await interaction.response.send_message("✅ Limpeza iniciada em background!", ephemeral=True)

    async def stop_stealth(self, interaction: discord.Interaction):
        if task_mgr.stop_task(self.user_id, "stealth"):
            await interaction.response.send_message("🛑 Limpeza abortada com sucesso.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nenhuma limpeza rodando.", ephemeral=True)
            
    async def start_farm(self, interaction: discord.Interaction):
        token = await self.get_active_token()
        config = get_user_data(self.user_id)
        if not token or not config.get('channel_id'):
            return await interaction.response.send_message("❌ Token ou Canal não configurados.", ephemeral=True)
            
        if task_mgr.is_running(self.user_id, "farm"):
            return await interaction.response.send_message("⚠️ Farm já está em andamento.", ephemeral=True)
            
        coro = auto_farm(token, config['channel_id'], self.user_id, ["up", "bump"], 15)
        task_mgr.add_task(self.user_id, "farm", coro)
        await interaction.response.send_message("✅ Auto-farm iniciado!", ephemeral=True)

    async def stop_farm(self, interaction: discord.Interaction):
        if task_mgr.stop_task(self.user_id, "farm"):
            await interaction.response.send_message("🛑 Farm parado.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nenhum farm rodando.", ephemeral=True)

    async def start_voice(self, interaction: discord.Interaction):
        token = await self.get_active_token()
        config = get_user_data(self.user_id)
        if not token or not config.get('channel_id'):
            return await interaction.response.send_message("❌ Token ou Canal não configurados.", ephemeral=True)

        if task_mgr.is_running(self.user_id, "voice"):
            return await interaction.response.send_message("⚠️ Você já está em uma call.", ephemeral=True)

        guild_id = interaction.guild_id
        if not guild_id:
            return await interaction.response.send_message("❌ Use este comando dentro do servidor onde deseja conectar na call.", ephemeral=True)

        user_id_str = str(await get_user_id_from_token(token))
        
        coro = start_voice_task(token, guild_id, config['channel_id'], user_id_str)
        task_mgr.add_task(self.user_id, "voice", coro)
        await interaction.response.send_message("🎧 Conectando sua conta à call...", ephemeral=True)

    async def stop_voice(self, interaction: discord.Interaction):
        if task_mgr.stop_task(self.user_id, "voice"):
            await interaction.response.send_message("🔇 Conta desconectada da call.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nenhuma call ativa.", ephemeral=True)

    async def add_token(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ConfigModal(self.user_id, "token", "Token da Conta"))
    
    async def set_channel(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ConfigModal(self.user_id, "channel", "ID do Canal"))
        
    async def set_webhook(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ConfigModal(self.user_id, "webhook", "URL do Webhook"))

    async def back(self, interaction: discord.Interaction):
        config = get_user_data(self.user_id)
        embed = self.cog._build_embed(interaction.user, config)
        await interaction.response.edit_message(embed=embed, view=PanelView(self.cog, self.user_id))

class ConfigModal(discord.ui.Modal):
    def __init__(self, user_id, config_type, title):
        super().__init__(title=title)
        self.user_id = user_id
        self.config_type = config_type
        
        self.input_data = discord.ui.TextInput(
            label="Insira o dado abaixo:",
            placeholder="Cole aqui...",
            required=True
        )
        self.add_item(self.input_data)

    async def on_submit(self, interaction: discord.Interaction):
        val = self.input_data.value.strip()
        data = get_user_data(self.user_id)
        
        if self.config_type == "token":
            tokens = data.get('tokens', [])
            tokens.append(encrypt(val))
            save_user_data(self.user_id, tokens=tokens, active_token_index=len(tokens)-1)
            msg = f"✅ Token salvo e ativado! (Conta {len(tokens)})"
            
        elif self.config_type == "channel":
            save_user_data(self.user_id, channel_id=int(val))
            msg = "✅ Canal salvo!"
            
        elif self.config_type == "webhook":
            save_user_data(self.user_id, webhook_url=val)
            msg = "✅ Webhook configurado!"

        await interaction.response.send_message(msg, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Panel(bot))
