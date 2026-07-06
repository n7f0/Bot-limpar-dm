import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncio
import os

# ============================================================
# CONFIGURAÇÃO DO BOT OFICIAL
# ============================================================
TOKEN_BOT = os.getenv('BOT_TOKEN')  # Token do bot oficial (começa com MT...)

if not TOKEN_BOT:
    print("❌ Defina a variável de ambiente BOT_TOKEN com o token do seu bot oficial.")
    exit(1)

intents = discord.Intents.default()
# Não precisamos de message_content para slash commands
bot = commands.Bot(command_prefix='!', intents=intents)

# Dicionário para armazenar dados por usuário
user_data = {}  # {user_id: {'token': str, 'chat_id': int, 'cleaning': bool}}

# ============================================================
# MODAL PARA INSERIR TOKEN
# ============================================================
class TokenModal(discord.ui.Modal, title='🔑 Configurar Token do Usuário'):
    token_input = discord.ui.TextInput(
        label='Cole seu token de usuário aqui',
        placeholder='Ex: NDIzNDU2Nzg5MDEyMzQ1Njc4.xyz...',
        style=discord.TextStyle.paragraph,
        required=True,
        min_length=50,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        token = self.token_input.value.strip()
        if interaction.user.id not in user_data:
            user_data[interaction.user.id] = {}
        user_data[interaction.user.id]['token'] = token
        await interaction.response.send_message(
            f'✅ Token configurado com sucesso!',
            ephemeral=True
        )
        # Atualizar o painel (se estiver aberto) - será feito pelo botão de atualização ou manualmente
        print(f'Token configurado para {interaction.user}')

# ============================================================
# MODAL PARA INSERIR ID DO CHAT
# ============================================================
class ChatModal(discord.ui.Modal, title='💬 Definir Chat DM'):
    chat_input = discord.ui.TextInput(
        label='ID do canal privado (DM)',
        placeholder='Ex: 123456789012345678',
        style=discord.TextStyle.short,
        required=True,
        min_length=17,
        max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            chat_id = int(self.chat_input.value.strip())
        except ValueError:
            await interaction.response.send_message('❌ ID inválido. Deve ser um número.', ephemeral=True)
            return

        if interaction.user.id not in user_data:
            user_data[interaction.user.id] = {}
        user_data[interaction.user.id]['chat_id'] = chat_id

        # Verificar se o canal existe e é DM (usando o token do usuário)
        token = user_data[interaction.user.id].get('token')
        if not token:
            await interaction.response.send_message(
                '❌ Primeiro configure seu token usando o botão "Configurar Token".',
                ephemeral=True
            )
            return

        headers = {'Authorization': token, 'Content-Type': 'application/json'}
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://discord.com/api/v10/channels/{chat_id}', headers=headers) as resp:
                if resp.status != 200:
                    await interaction.response.send_message(
                        '❌ Canal não encontrado ou você não tem acesso. Verifique o ID.',
                        ephemeral=True
                    )
                    return
                data = await resp.json()
                if data.get('type') != 1:  # 1 = DM
                    await interaction.response.send_message('❌ O ID fornecido não é uma DM privada.', ephemeral=True)
                    return

        await interaction.response.send_message(
            f'✅ Chat definido com sucesso! (ID: {chat_id})',
            ephemeral=True
        )
        print(f'Chat definido para {interaction.user}: {chat_id}')

# ============================================================
# VIEW DO PAINEL (com botões)
# ============================================================
class PainelView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)  # Timeout None para manter os botões ativos
        self.user_id = user_id

    @discord.ui.button(label='🔑 Configurar Token', style=discord.ButtonStyle.primary, custom_id='config_token')
    async def config_token_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('❌ Este painel é pessoal.', ephemeral=True)
            return
        await interaction.response.send_modal(TokenModal())

    @discord.ui.button(label='💬 Definir Chat DM', style=discord.ButtonStyle.success, custom_id='set_chat')
    async def set_chat_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('❌ Este painel é pessoal.', ephemeral=True)
            return
        await interaction.response.send_modal(ChatModal())

    @discord.ui.button(label='🧹 Iniciar Limpeza', style=discord.ButtonStyle.danger, custom_id='start_clean')
    async def start_clean_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('❌ Este painel é pessoal.', ephemeral=True)
            return

        # Verificar se token e chat estão configurados
        data = user_data.get(self.user_id, {})
        token = data.get('token')
        chat_id = data.get('chat_id')

        if not token:
            await interaction.response.send_message('❌ Token não configurado. Use o botão "Configurar Token".', ephemeral=True)
            return
        if not chat_id:
            await interaction.response.send_message('❌ Chat não definido. Use o botão "Definir Chat DM".', ephemeral=True)
            return

        # Verificar se já está em limpeza
        if data.get('cleaning', False):
            await interaction.response.send_message('⏳ Uma limpeza já está em andamento.', ephemeral=True)
            return

        # Iniciar limpeza
        await interaction.response.defer(ephemeral=False)  # Resposta pública (não ephemeral) para ver o progresso

        # Enviar mensagem inicial de progresso
        progress_msg = await interaction.followup.send(
            f'🔄 **Iniciando limpeza...**\nChat: {chat_id}\n0 mensagens deletadas'
        )

        # Marcar como em limpeza
        user_data[self.user_id]['cleaning'] = True

        # Executar limpeza em background
        bot.loop.create_task(
            self.clean_dm(
                interaction=interaction,
                token=token,
                chat_id=chat_id,
                progress_msg=progress_msg
            )
        )

    async def clean_dm(self, interaction: discord.Interaction, token: str, chat_id: int, progress_msg: discord.Message):
        """Função assíncrona que faz a limpeza e atualiza o progresso."""
        user_id = self.user_id
        headers = {'Authorization': token, 'Content-Type': 'application/json'}
        messages_deleted = 0
        last_id = None
        total_fetched = 0
        max_messages = 1000  # Limite seguro para não sobrecarregar

        try:
            async with aiohttp.ClientSession() as session:
                while True:
                    # Buscar lote de mensagens (100 por vez)
                    url = f'https://discord.com/api/v10/channels/{chat_id}/messages?limit=100'
                    if last_id:
                        url += f'&before={last_id}'
                    async with session.get(url, headers=headers) as resp:
                        if resp.status != 200:
                            await progress_msg.edit(content=f'❌ Erro ao buscar mensagens: {resp.status}')
                            break
                        messages = await resp.json()
                        if not messages:
                            break

                        total_fetched += len(messages)
                        for msg in messages:
                            if msg['author']['id'] == str(user_id):
                                # Deletar mensagem
                                del_url = f'https://discord.com/api/v10/channels/{chat_id}/messages/{msg["id"]}'
                                async with session.delete(del_url, headers=headers) as del_resp:
                                    if del_resp.status == 204:
                                        messages_deleted += 1
                                    else:
                                        print(f'Falha ao deletar {msg["id"]}: {del_resp.status}')
                                # Pausa de 0.2 segundos entre deleções para evitar rate-limit
                                await asyncio.sleep(0.2)

                            # Atualizar progresso a cada 5 mensagens deletadas
                            if messages_deleted % 5 == 0 and messages_deleted > 0:
                                await progress_msg.edit(
                                    content=f'🔄 **Limpando...**\nChat: {chat_id}\n'
                                            f'✅ {messages_deleted} mensagens deletadas\n'
                                            f'📊 {total_fetched} mensagens analisadas'
                                )

                        last_id = messages[-1]['id']
                        if len(messages) < 100:
                            break

            # Finalizado
            await progress_msg.edit(
                content=f'✅ **Limpeza concluída!**\n'
                        f'Chat: {chat_id}\n'
                        f'🗑️ {messages_deleted} mensagens deletadas\n'
                        f'📊 {total_fetched} mensagens analisadas'
            )
            user_data[self.user_id]['cleaning'] = False

        except Exception as e:
            await progress_msg.edit(content=f'❌ Erro durante a limpeza: {str(e)}')
            user_data[self.user_id]['cleaning'] = False
            raise

# ============================================================
# COMANDO SLASH /paineldm
# ============================================================
@bot.tree.command(name='paineldm', description='Abre o painel de controle para limpeza de DMs')
async def paineldm(interaction: discord.Interaction):
    """Envia o painel com botões para o usuário."""
    view = PainelView(interaction.user.id)
    embed = discord.Embed(
        title='🛠️ Painel de Limpeza de DM',
        description='Use os botões abaixo para configurar e iniciar a limpeza.',
        color=discord.Color.blue()
    )
    embed.add_field(name='🔑 Token', value='*Não configurado*' if not user_data.get(interaction.user.id, {}).get('token') else '✅ Configurado', inline=True)
    embed.add_field(name='💬 Chat ID', value='*Não definido*' if not user_data.get(interaction.user.id, {}).get('chat_id') else f'`{user_data[interaction.user.id]["chat_id"]}`', inline=True)
    embed.set_footer(text='Clique nos botões para interagir.')

    await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

# ============================================================
# EVENTO DE PRONTO E SINCRONIZAÇÃO
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