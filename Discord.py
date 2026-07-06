import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncio
import os
import random
import time

# ============================================================
# CONFIGURAÇÃO DO BOT OFICIAL
# ============================================================
TOKEN_BOT = os.getenv('BOT_TOKEN')
if not TOKEN_BOT:
    print("❌ Defina a variável de ambiente BOT_TOKEN.")
    exit(1)

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

# ============================================================
# ESTRUTURA DE DADOS
# ============================================================
user_data = {}  # {user_id: {'token': str, 'chat_id': int, 'cleaning': bool, 'cancel_event': asyncio.Event}}

# ============================================================
# MODAIS
# ============================================================
class TokenModal(discord.ui.Modal, title='🔑 Configurar Token do Usuário'):
    token_input = discord.ui.TextInput(
        label='Cole seu token de usuário aqui',
        placeholder='Ex: NDIzNDU2Nzg5MDEyMzQ1Njc4.xyz...',
        style=discord.TextStyle.paragraph,
        required=True,
        min_length=50
    )
    async def on_submit(self, interaction: discord.Interaction):
        token = self.token_input.value.strip()
        if interaction.user.id not in user_data:
            user_data[interaction.user.id] = {}
        user_data[interaction.user.id]['token'] = token
        await interaction.response.send_message('✅ Token configurado!', ephemeral=True)
        # Atualizar o painel se existir
        await update_painel(interaction)

class ChatModal(discord.ui.Modal, title='💬 Definir Chat DM'):
    chat_input = discord.ui.TextInput(
        label='ID do canal privado (DM)',
        placeholder='Ex: 123456789012345678',
        style=discord.TextStyle.short,
        required=True
    )
    async def on_submit(self, interaction: discord.Interaction):
        try:
            chat_id = int(self.chat_input.value.strip())
        except ValueError:
            await interaction.response.send_message('❌ ID inválido.', ephemeral=True)
            return

        user_id = interaction.user.id
        if user_id not in user_data:
            user_data[user_id] = {}
        token = user_data[user_id].get('token')
        if not token:
            await interaction.response.send_message('❌ Configure o token primeiro.', ephemeral=True)
            return

        # Verificar se é DM
        headers = {'Authorization': token, 'Content-Type': 'application/json'}
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://discord.com/api/v10/channels/{chat_id}', headers=headers) as resp:
                if resp.status != 200:
                    await interaction.response.send_message('❌ Canal não encontrado.', ephemeral=True)
                    return
                data = await resp.json()
                if data.get('type') != 1:
                    await interaction.response.send_message('❌ Não é uma DM.', ephemeral=True)
                    return

        user_data[user_id]['chat_id'] = chat_id
        await interaction.response.send_message(f'✅ Chat definido: {chat_id}', ephemeral=True)
        await update_painel(interaction)

# ============================================================
# PAINEL (VIEW) COM BOTÕES
# ============================================================
class PainelView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

    # Botão Configurar Token
    @discord.ui.button(label='🔑 Token', style=discord.ButtonStyle.primary)
    async def token_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('❌ Privado.', ephemeral=True)
            return
        await interaction.response.send_modal(TokenModal())

    # Botão Definir Chat
    @discord.ui.button(label='💬 Chat', style=discord.ButtonStyle.success)
    async def chat_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('❌ Privado.', ephemeral=True)
            return
        await interaction.response.send_modal(ChatModal())

    # Botão Iniciar Limpeza
    @discord.ui.button(label='🧹 Iniciar', style=discord.ButtonStyle.danger)
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('❌ Privado.', ephemeral=True)
            return
        data = user_data.get(self.user_id, {})
        token = data.get('token')
        chat_id = data.get('chat_id')
        if not token or not chat_id:
            await interaction.response.send_message('❌ Configure token e chat primeiro.', ephemeral=True)
            return
        if data.get('cleaning', False):
            await interaction.response.send_message('⏳ Já em andamento.', ephemeral=True)
            return

        # Marcar como limpeza ativa
        user_data[self.user_id]['cleaning'] = True
        user_data[self.user_id]['cancel_event'] = asyncio.Event()

        await interaction.response.defer(ephemeral=False)
        progress_msg = await interaction.followup.send('🔄 **Preparando...**')

        # Iniciar tarefa de limpeza
        bot.loop.create_task(
            self.perform_cleanup(interaction, token, chat_id, progress_msg)
        )

    async def perform_cleanup(self, interaction, token, chat_id, progress_msg):
        user_id = self.user_id
        cancel_event = user_data[user_id].get('cancel_event')
        headers = {'Authorization': token, 'Content-Type': 'application/json'}

        messages_deleted = 0
        total_fetched = 0
        max_messages = 2000  # limite de segurança
        start_time = time.time()
        last_id = None

        async with aiohttp.ClientSession() as session:
            while True:
                # Verificar cancelamento
                if cancel_event and cancel_event.is_set():
                    await progress_msg.edit(content='⏹️ **Limpeza cancelada pelo usuário.**')
                    break

                # Buscar lote
                url = f'https://discord.com/api/v10/channels/{chat_id}/messages?limit=100'
                if last_id:
                    url += f'&before={last_id}'
                try:
                    async with session.get(url, headers=headers) as resp:
                        if resp.status != 200:
                            await progress_msg.edit(content=f'❌ Erro {resp.status}')
                            break
                        messages = await resp.json()
                        if not messages:
                            break
                except Exception as e:
                    await progress_msg.edit(content=f'❌ Erro: {e}')
                    break

                total_fetched += len(messages)
                for msg in messages:
                    if cancel_event and cancel_event.is_set():
                        break
                    if msg['author']['id'] == str(user_id):
                        del_url = f'https://discord.com/api/v10/channels/{chat_id}/messages/{msg["id"]}'
                        try:
                            async with session.delete(del_url, headers=headers) as del_resp:
                                if del_resp.status == 204:
                                    messages_deleted += 1
                                else:
                                    print(f'Falha deletar {msg["id"]}: {del_resp.status}')
                        except Exception:
                            pass
                        # Pausa aleatória entre 0.2s e 0.8s
                        await asyncio.sleep(random.uniform(0.2, 0.8))

                    # Atualizar progresso a cada 3 mensagens
                    if messages_deleted % 3 == 0 and messages_deleted > 0:
                        await self.update_progress(progress_msg, messages_deleted, total_fetched, max_messages, start_time)

                    # Limite de segurança
                    if messages_deleted >= max_messages:
                        await progress_msg.edit(content=f'⚠️ **Limite atingido ({max_messages} mensagens).**')
                        user_data[user_id]['cleaning'] = False
                        return

                last_id = messages[-1]['id']
                if len(messages) < 100:
                    break

        # Fim da limpeza
        elapsed = time.time() - start_time
        await progress_msg.edit(
            content=f'✅ **Limpeza concluída!**\n'
                    f'🗑️ {messages_deleted} mensagens deletadas\n'
                    f'📊 {total_fetched} mensagens analisadas\n'
                    f'⏱️ Tempo: {elapsed:.1f}s'
        )
        user_data[user_id]['cleaning'] = False

    async def update_progress(self, msg, deleted, fetched, max_msgs, start_time):
        percent = min(100, int((deleted / max_msgs) * 100))
        bar_len = 20
        filled = int(bar_len * percent / 100)
        bar = '█' * filled + '░' * (bar_len - filled)
        elapsed = time.time() - start_time
        speed = deleted / elapsed if elapsed > 0 else 0
        await msg.edit(
            content=f'🔄 **Limpando...**\n'
                    f'`{bar}` {percent}%\n'
                    f'🗑️ {deleted} deletadas | 📊 {fetched} analisadas\n'
                    f'⚡ {speed:.1f} msg/s | ⏱️ {elapsed:.1f}s'
        )

    # Botão Cancelar (será adicionado separadamente)
    @discord.ui.button(label='⏹️ Cancelar', style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('❌ Privado.', ephemeral=True)
            return
        data = user_data.get(self.user_id, {})
        if not data.get('cleaning', False):
            await interaction.response.send_message('❌ Nenhuma limpeza em andamento.', ephemeral=True)
            return
        cancel_event = data.get('cancel_event')
        if cancel_event:
            cancel_event.set()
            await interaction.response.send_message('⏹️ Cancelando...', ephemeral=True)
        else:
            await interaction.response.send_message('❌ Erro ao cancelar.', ephemeral=True)

# ============================================================
# FUNÇÃO PARA ATUALIZAR O PAINEL (embed)
# ============================================================
async def update_painel(interaction):
    # Reenvia o painel atualizado (opcional)
    pass

# ============================================================
# COMANDO /paineldm
# ============================================================
@bot.tree.command(name='paineldm', description='Abre o painel de controle de limpeza de DMs')
async def paineldm(interaction: discord.Interaction):
    view = PainelView(interaction.user.id)
    data = user_data.get(interaction.user.id, {})
    token_status = '✅' if data.get('token') else '❌'
    chat_status = f'`{data.get("chat_id")}`' if data.get('chat_id') else '❌'
    cleaning_status = '⏳ Em andamento' if data.get('cleaning') else '✅ Parado'

    embed = discord.Embed(
        title='🛠️ Painel de Limpeza de DM',
        description='Configure e inicie a limpeza de mensagens.',
        color=discord.Color.blue()
    )
    embed.add_field(name='🔑 Token', value=token_status, inline=True)
    embed.add_field(name='💬 Chat ID', value=chat_status, inline=True)
    embed.add_field(name='🧹 Status', value=cleaning_status, inline=True)
    embed.set_footer(text='Use os botões abaixo.')

    await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

# ============================================================
# INICIALIZAÇÃO
# ============================================================
@bot.event
async def on_ready():
    print(f'✅ Logado como {bot.user}')
    await bot.tree.sync()
    print('📌 Comandos sincronizados.')

if __name__ == "__main__":
    bot.run(TOKEN_BOT)