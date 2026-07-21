import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger(__name__)

class Panel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="paineldm", description="Exibe o painel de controle no servidor")
    async def paineldm(self, interaction: discord.Interaction):
        """Envia o painel com botões para o canal atual."""
        embed = discord.Embed(
            title="🛡️ Painel de Controle - Gerenciamento e Limpeza",
            description="Utilize os botões abaixo para interagir com o sistema diretamente por este canal.",
            color=0x58B3FF  # azul
        )
        embed.add_field(name="Status do Servidor", value="🟢 Online e Operacional", inline=True)
        embed.add_field(name="Disponibilidade", value="24/7 Ativo", inline=True)
        embed.set_footer(text="Painel Público do Servidor")

        # Cria uma View com um botão (pode adicionar mais depois)
        view = discord.ui.View()
        button = discord.ui.Button(
            label="🧹 Iniciar Ação",
            style=discord.ButtonStyle.primary,
            custom_id="btn_limpar"
        )
        view.add_item(button)

        # Envia a mensagem com embed e botão
        await interaction.response.send_message(embed=embed, view=view)
        logger.info(f"Painel enviado no canal {interaction.channel.id} por {interaction.user}")

    # Opcional: callback para o botão (exemplo)
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.component:
            if interaction.data.get("custom_id") == "btn_limpar":
                await interaction.response.send_message("Ação de limpeza iniciada!", ephemeral=True)
                # Aqui você chama sua lógica de limpeza

async def setup(bot):
    await bot.add_cog(Panel(bot))