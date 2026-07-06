import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncio
import os

# ============================================================
# CONFIGURAÇÃO DO BOT OFICIAL
# ============================================================
TOKEN_BOT = os.getenv('BOT_TOKEN')  # Token do bot oficial (MT...)
if not TOKEN_BOT:
    print("❌ Defina a variável de ambiente BOT_TOKEN com o token do seu bot oficial.")
    exit(1)

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

# Dicionário para armazenar dados por usuário
user_data = {}  # {user_id: {"token": str, "channel_id": int, "deleting": bool}}

# ============================================================
# MODAL PARA INSERIR TOKEN
# ============================================================
class TokenModal(discord.ui.Modal, title='🔑 Inserir Token do Usuário'):
    token_input = discord.ui.TextInput(
        label='Cole seu token de usuário (self-bot)',
        placeholder='Token obtido pelo navegador',
        style=discord.TextStyle.paragraph,
        required=True,
        min_length=50,
        max_length=200
    )

    async def on_submit(self, interaction: discord.Interaction):
        token = self.token_input.value.strip()
        user_id = interaction.user.id
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['token'] = token
        # Limpa channel_id anterior se existir
        user_data[user_id].pop('channel_id', None)
        await interaction.response.send_message(
            f'✅ Token configurado! Agora clique no botão abaixo para definir o chat a ser limpo.',
            ephemeral=True,
            view=ChatSetupView(user_id)
        )

# ============================================================
# VIEW: BOTÃO PARA DEFINIR CHAT
# ============================================================
class ChatSetupView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=300)  # 5 minutos para responder
        self.user_id = user_id

    @discord.ui.button(label='📌 Definir Chat (ID da DM)', style=discord.ButtonStyle.primary)
    async def define_chat(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Esse botão não é para você.", ephemeral=True)
            return
        # Abre modal para inserir o ID do canal
        await interaction.response.send_modal(ChatIDModal(self.user_id))

# ============================================================
# MODAL PARA INSERIR ID DO CHAT
# ============================================================
class ChatIDModal(discord.ui.Modal, title='📌 ID do Chat Privado'):
    chat_id_input = discord.ui.TextInput(
        label='Cole o ID do chat (DM)',
        placeholder='Ex: 123456789012345678',
        style=discord.TextStyle.short,
        required=True,
        min_length=17,
        max_length=20
    )

    def __init__(self, user_id):
        super().__init__()
        self.user_id = user_id

    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel_id = int(self.chat_id_input.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ ID inválido. Deve ser um número.", ephemeral=True)
            return
        # Salva o channel_id
        if self.user_id not in user_data:
            user_data[self.user_id] = {}
        user_data[self.user_id]['channel_id'] = channel_id
        await interaction.response.send_message(
            f'✅ Chat definido (ID: {channel_id}). Agora clique em "Iniciar Limpeza" para começar.',
            ephemeral=True,
            view=CleanupStartView(self.user_id)
        )

# ============================================================
# VIEW: BOTÃO INICIAR LIMPEZA
# ============================================================
class CleanupStartView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=300)
        self.user_id = user_id

    @discord.ui.button(label='🧹 Iniciar Limpeza', style=discord.ButtonStyle.danger)
    async def start_cleanup(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Esse botão não é para você.", ephemeral=True)
            return
        # Verifica se já está em processo
        if user_data.get(self.user_id, {}).get('deleting', False):
            await interaction.response.send_message("⚠️ Uma limpeza já está em andamento.", ephemeral=True)
            return
        # Dispara a limpeza
        await interaction.response.send_message("🔍 Iniciando limpeza...", ephemeral=True)
        # Inicia a tarefa de limpeza (em background)
        bot.loop.create_task(perform_cleanup(interaction, self.user_id))

# ============================================================
# FUNÇÃO DE LIMPEZA (com progresso e delay)
# ============================================================
async def perform_cleanup(interaction: discord.Interaction, user_id: int):
    user = user_data.get(user_id)
    if not user or 'token' not in user or 'channel_id' not in user:
        await interaction.followup.send("❌ Token ou chat não configurados.", ephemeral=True)
        return

    token = user['token']
    channel_id = user['channel_id']
    # Marca como em progresso
    user['deleting'] = True

    # Mensagem de progresso (será editada)
    progress_msg = await interaction.followup.send("🔄 Preparando...", ephemeral=True)

    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    async with aiohttp.ClientSession() as session:
        # Verifica o canal
        async with session.get(f'https://discord.com/api/v10/channels/{channel_id}', headers=headers) as resp:
            if resp.status != 200:
                await progress_msg.edit(content="❌ Canal não encontrado ou sem acesso.")
                user['deleting'] = False
                return
            channel_data = await resp.json()
            if channel_data.get('type') != 1:
                await progress_msg.edit(content="❌ O ID não é de uma DM.")
                user['deleting'] = False
                return

        # Busca mensagens até um limite máximo (ex: 1000)
        max_messages = 1000
        deleted = 0
        last_id = None
        total_fetched = 0

        while True:
            url = f'https://discord.com/api/v10/channels/{channel_id}/messages?limit=100'
            if last_id:
                url += f'&before={last_id}'
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    await progress_msg.edit(content=f"❌ Erro ao buscar mensagens: {resp.status}")
                    user['deleting'] = False
                    return
                messages = await resp.json()
                if not messages:
                    break
                total_fetched += len(messages)

                # Filtra apenas mensagens do usuário (self)
                user_messages = [m for m in messages if m['author']['id'] == str(user_id)]
                for msg in user_messages:
                    if deleted >= max_messages:
                        break
                    del_url = f'https://discord.com/api/v10/channels/{channel_id}/messages/{msg["id"]}'
                    async with session.delete(del_url, headers=headers) as del_resp:
                        if del_resp.status == 204:
                            deleted += 1
                        else:
                            print(f"Erro ao deletar {msg['id']}: {del_resp.status}")
                    # Delay de 0.5 segundos entre cada deleção (temporizador)
                    await asyncio.sleep(0.5)

                    # Atualiza progresso a cada 5 mensagens
                    if deleted % 5 == 0 or deleted == max_messages:
                        progress = min(deleted / max_messages * 100, 100)
                        bar = "🟩" * int(progress // 10) + "⬜" * (10 - int(progress // 10))
                        await progress_msg.edit(
                            content=f"🧹 Deletando mensagens...\n"
                                    f"Progresso: {bar} {deleted}/{max_messages} (max)\n"
                                    f"Último lote: {len(messages)} mensagens buscadas."
                        )

                    if deleted >= max_messages:
                        break

                last_id = messages[-1]['id']
                if len(messages) < 100 or deleted >= max_messages:
                    break

        # Finalizado
        user['deleting'] = False
        await progress_msg.edit(
            content=f"✅ Limpeza concluída! Deletadas **{deleted}** mensagens suas (limite de {max_messages})."
        )

# ============================================================
# COMANDO SLASH: /configurar
# ============================================================
@bot.tree.command(name='configurar', description='Configurar token e chat para limpeza')
async def configurar(interaction: discord.Interaction):
    """Envia uma mensagem com botão para inserir token."""
    # Cria uma view com botão
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label='🔑 Inserir Token', style=discord.ButtonStyle.primary, custom_id='token_btn'))

    # Definimos uma callback para o botão
    async def token_callback(interaction: discord.Interaction):
        if interaction.user.id != interaction.user.id:
            await interaction.response.send_message("❌ Não autorizado.", ephemeral=True)
            return
        await interaction.response.send_modal(TokenModal())

    # Atribui a callback ao botão (precisa ser feito via view com um botão customizado)
    # Vou refazer com uma classe View para simplificar
    await interaction.response.send_message(
        "Clique no botão abaixo para inserir seu token de usuário.",
        ephemeral=True,
        view=TokenSetupView()
    )

# ============================================================
# VIEW PARA O BOTÃO DE TOKEN
# ============================================================
class TokenSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=600)

    @discord.ui.button(label='🔑 Inserir Token', style=discord.ButtonStyle.primary)
    async def token_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TokenModal())

# ============================================================
# COMANDO DE AJUDA (opcional)
# ============================================================
@bot.tree.command(name='ajuda', description='Como usar o bot')
async def ajuda(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 Bot de Limpeza de DM",
        description="Passos para usar:\n"
                    "1. Use `/configurar` e clique em 'Inserir Token'.\n"
                    "2. Cole o token do seu usuário (self-bot).\n"
                    "3. Depois, clique em 'Definir Chat' e cole o ID da DM.\n"
                    "4. Clique em 'Iniciar Limpeza'.\n"
                    "5. Acompanhe o progresso!",
        color=0x00ff00
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ============================================================
# EVENTO ON_READY E SINCRONIZAÇÃO
# ============================================================
@bot.event
async def on_ready():
    print(f'✅ Bot oficial logado como {bot.user} (ID: {bot.user.id})')
    await bot.tree.sync()
    print('📌 Comandos slash sincronizados.')

# ============================================================
# INICIALIZAÇÃO
# ============================================================
if __name__ == "__main__":
    bot.run(TOKEN_BOT)