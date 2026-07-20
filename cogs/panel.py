import discord
from discord import app_commands
from discord.ext import commands
from utils.db import get_user, save_user
from models.user import User
import asyncio

class Panel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='painel', description='Abre o painel de controle com status em tempo real')
    async def painel(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user = User(interaction.user.id)
        embed = self._build_dashboard(user)
        view = DashboardView(user)
        await interaction.followup.send(embed=embed, view=view)

    def _build_dashboard(self, user):
        tokens = user.data.get('tokens', [])
        default_idx = user.data.get('default_token_index', 0)
        status = "✅ Ativo" if tokens else "❌ Nenhum token"
        embed = discord.Embed(
            title="🛡️ Dashboard - Modo Stealth Pro",
            color=discord.Color.blue()
        )
        embed.add_field(name="Tokens", value=f"{len(tokens)} configurados", inline=True)
        embed.add_field(name="Token Ativo", value=f"#{default_idx+1}" if tokens else "Nenhum", inline=True)
        embed.add_field(name="Canal de Limpeza", value=f"<#{user.data.get('chat_id')}>" if user.data.get('chat_id') else "Não definido", inline=False)
        embed.add_field(name="Auto-Farm", value="✅ Ativo" if user.data.get('auto_farming') else "❌ Inativo", inline=True)
        embed.add_field(name="Modo Sono", value="💤 Ativo" if user.data.get('sleep_mode') else "☀️ Inativo", inline=True)
        embed.set_footer(text="Use os botões abaixo para gerenciar")
        return embed

class DashboardView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=300)
        self.user = user
        self.add_item(TokenSelect(user))
        self.add_item(discord.ui.Button(label="➕ Adicionar Token", style=discord.ButtonStyle.success, custom_id="add_token"))
        self.add_item(discord.ui.Button(label="🗑️ Remover Token", style=discord.ButtonStyle.danger, custom_id="remove_token"))
        self.add_item(discord.ui.Button(label="🔄 Atualizar", style=discord.ButtonStyle.secondary, custom_id="refresh"))

    async def interaction_check(self, interaction):
        return interaction.user.id == self.user.user_id

class TokenSelect(discord.ui.Select):
    def __init__(self, user):
        tokens = user.data.get('tokens', [])
        options = []
        for i, token in enumerate(tokens):
            # Mostra apenas os primeiros 10 caracteres do token
            label = f"Token {i+1} - {token[:10]}..."
            options.append(discord.SelectOption(label=label, value=str(i), default=(i == user.data.get('default_token_index', 0))))
        super().__init__(placeholder="Selecione o token ativo", options=options)

    async def callback(self, interaction: discord.Interaction):
        idx = int(self.values[0])
        self.user.data['default_token_index'] = idx
        self.user.save()
        embed = interaction.message.embeds[0]
        embed.set_field_at(1, name="Token Ativo", value=f"#{idx+1}", inline=True)
        await interaction.response.edit_message(embed=embed, view=self.view)