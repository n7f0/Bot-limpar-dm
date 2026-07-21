import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncio

logger = logging.getLogger(__name__)

class Panel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ========== COMANDO SLASH ==========
    @app_commands.command(name="paineldm", description="Exibe o painel de controle no servidor")
    async def paineldm(self, interaction: discord.Interaction):
        """Envia o painel com botões no canal atual."""
        embed = discord.Embed(
            title="🛡️ Nexzy Store - Painel de Controle",
            description="Gerencie mensagens, canais e muito mais com um clique.",
            color=0x3b82f6  # azul Nexzy
        )
        embed.add_field(name="📊 Status", value="🟢 Online e operacional", inline=True)
        embed.add_field(name="⏳ Uptime", value="24/7 Ativo", inline=True)
        embed.add_field(name="👥 Usuários", value=f"{len(interaction.guild.members)} membros", inline=True)
        embed.set_footer(text="Nexzy Store Clear • v1.0")
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        view = discord.ui.View(timeout=None)

        # Botão: Limpar mensagens do bot
        btn_clean_bot = discord.ui.Button(
            label="🧹 Limpar mensagens do bot",
            style=discord.ButtonStyle.primary,
            custom_id="clean_bot"
        )
        # Botão: Limpar mensagens de um usuário
        btn_clean_user = discord.ui.Button(
            label="👤 Limpar mensagens de usuário",
            style=discord.ButtonStyle.secondary,
            custom_id="clean_user"
        )
        # Botão: Entrar na call (voz)
        btn_voice = discord.ui.Button(
            label="🔊 Entrar na call",
            style=discord.ButtonStyle.success,
            custom_id="join_voice"
        )
        # Botão: Sair da call
        btn_leave = discord.ui.Button(
            label="🔇 Sair da call",
            style=discord.ButtonStyle.danger,
            custom_id="leave_voice"
        )

        view.add_item(btn_clean_bot)
        view.add_item(btn_clean_user)
        view.add_item(btn_voice)
        view.add_item(btn_leave)

        await interaction.response.send_message(embed=embed, view=view)
        logger.info(f"Painel enviado por {interaction.user} no canal {interaction.channel.id}")

    # ========== HANDLER DOS BOTÕES ==========
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return

        custom_id = interaction.data.get("custom_id")

        # ---------- LIMPAR MENSAGENS DO BOT ----------
        if custom_id == "clean_bot":
            await interaction.response.defer(ephemeral=True)
            channel = interaction.channel
            if not isinstance(channel, discord.TextChannel):
                await interaction.followup.send("❌ Este comando só funciona em canais de texto.", ephemeral=True)
                return

            # Permissão necessária: gerenciar mensagens
            if not channel.permissions_for(interaction.guild.me).manage_messages:
                await interaction.followup.send("❌ Eu não tenho permissão para gerenciar mensagens neste canal.", ephemeral=True)
                return

            # Buscar mensagens do próprio bot
            def is_bot_message(msg):
                return msg.author == self.bot.user

            deleted = 0
            async for msg in channel.history(limit=1000):
                if is_bot_message(msg):
                    try:
                        await msg.delete()
                        deleted += 1
                        await asyncio.sleep(0.5)  # evitar rate limit
                    except:
                        pass

            await interaction.followup.send(f"✅ {deleted} mensagens do bot foram apagadas.", ephemeral=True)

        # ---------- LIMPAR MENSAGENS DE UM USUÁRIO ----------
        elif custom_id == "clean_user":
            # Abrir um modal para o usuário digitar o ID
            modal = CleanUserModal()
            await interaction.response.send_modal(modal)

        # ---------- ENTRAR NA CALL ----------
        elif custom_id == "join_voice":
            await interaction.response.defer(ephemeral=True)

            member = interaction.user
            voice_state = member.voice
            if not voice_state or not voice_state.channel:
                await interaction.followup.send("❌ Você não está em um canal de voz.", ephemeral=True)
                return

            channel = voice_state.channel
            if interaction.guild.voice_client is not None:
                await interaction.followup.send("⚠️ Eu já estou em um canal de voz.", ephemeral=True)
                return

            try:
                await channel.connect()
                await interaction.followup.send(f"✅ Conectado ao canal `{channel.name}`!", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Erro ao conectar: {e}", ephemeral=True)

        # ---------- SAIR DA CALL ----------
        elif custom_id == "leave_voice":
            await interaction.response.defer(ephemeral=True)

            if interaction.guild.voice_client is None:
                await interaction.followup.send("❌ Eu não estou em nenhum canal de voz.", ephemeral=True)
                return

            await interaction.guild.voice_client.disconnect()
            await interaction.followup.send("🔇 Desconectado do canal de voz.", ephemeral=True)


# ========== MODAL PARA LIMPAR MENSAGENS DE UM USUÁRIO ==========
class CleanUserModal(discord.ui.Modal, title="Limpar mensagens de um usuário"):
    user_id = discord.ui.TextInput(
        label="ID do usuário",
        placeholder="Digite o ID numérico do usuário",
        required=True,
        min_length=17,
        max_length=20
    )
    limit = discord.ui.TextInput(
        label="Quantidade máxima (opcional)",
        placeholder="Deixe em branco para até 1000",
        required=False,
        default="100"
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.followup.send("❌ Este comando só funciona em canais de texto.", ephemeral=True)
            return

        # Verificar permissão
        if not channel.permissions_for(interaction.guild.me).manage_messages:
            await interaction.followup.send("❌ Eu não tenho permissão para gerenciar mensagens.", ephemeral=True)
            return

        try:
            target_id = int(self.user_id.value)
        except ValueError:
            await interaction.followup.send("❌ ID inválido. Deve ser um número.", ephemeral=True)
            return

        limit = 100
        if self.limit.value:
            try:
                limit = int(self.limit.value)
                if limit < 1:
                    limit = 100
                elif limit > 1000:
                    limit = 1000
            except:
                limit = 100

        target = interaction.guild.get_member(target_id)
        if not target:
            # Tenta buscar via API
            try:
                target = await interaction.guild.fetch_member(target_id)
            except:
                await interaction.followup.send("❌ Não encontrei este usuário no servidor.", ephemeral=True)
                return

        def is_target_message(msg):
            return msg.author == target

        deleted = 0
        async for msg in channel.history(limit=limit):
            if is_target_message(msg):
                try:
                    await msg.delete()
                    deleted += 1
                    await asyncio.sleep(0.5)
                except:
                    pass

        await interaction.followup.send(f"✅ {deleted} mensagens de {target.display_name} foram apagadas.", ephemeral=True)


# ========== SETUP DA COG ==========
async def setup(bot):
    await bot.add_cog(Panel(bot))