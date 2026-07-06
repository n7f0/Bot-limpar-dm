import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncio
import os
import time
from datetime import datetime

# ============================================================
# CONFIGURAÇÃO
# ============================================================
TOKEN_BOT = os.getenv('BOT_TOKEN')
if not TOKEN_BOT:
    print("❌ Defina a variável BOT_TOKEN.")
    exit(1)

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

user_data = {}  # {user_id: {'token': str, 'chat_id': int, 'cleaning': bool, 'cancel': bool}}

# ============================================================
# MODAIS
# ============================================================
class TokenModal(discord.ui.Modal, title='🔑 Configurar Token'):
    token_input = discord.ui.TextInput(label='Token', style=discord.TextStyle.paragraph, required=True, min_length=50, max_length=100)
    async def on_submit(self, interaction: discord.Interaction):
        token = self.token_input.value.strip()
        if interaction.user.id not in user_data:
            user_data[interaction.user.id] = {}
        user_data[interaction.user.id]['token'] = token
        await interaction.response.send_message('✅ Token configurado.', ephemeral=True)

class ChatModal(discord.ui.Modal, title='💬 Definir Chat DM'):
    chat_input = discord.ui.TextInput(label='ID do Canal', placeholder='123456789012345678', required=True, min_length=17, max_length=20)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            chat_id = int(self.chat_input.value.strip())
        except ValueError:
            await interaction.response.send_message('❌ ID inválido.', ephemeral=True)
            return
        if interaction.user.id not in user_data:
            user_data[interaction.user.id] = {}
        user_data[interaction.user.id]['chat_id'] = chat_id
        # Validar canal
        token = user_data[interaction.user.id].get('token')
        if not token:
            await interaction.response.send_message('❌ Configure o token primeiro.', ephemeral=True)
            return
        headers = {'Authorization': token, 'Content-Type': 'application/json'}
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://discord.com/api/v10/channels/{chat_id}', headers=headers) as resp:
                if resp.status != 200:
                    await interaction.response.send_message('❌ Canal não encontrado ou sem acesso.', ephemeral=True)
                    return
                data = await resp.json()
                if data.get('type') != 1:
                    await interaction.response.send_message('❌ Não é uma DM.', ephemeral=True)
                    return
        await interaction.response.send_message(f'✅ Chat definido: {chat_id}', ephemeral=True)

# ============================================================
# VIEW DO PAINEL
# ============================================================
class PainelView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label='🔑 Token', style=discord.ButtonStyle.primary, custom_id='token_btn')
    async def token_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('❌ Não autorizado.', ephemeral=True)
            return
        await interaction.response.send_modal(TokenModal())

    @discord.ui.button(label='💬 Chat', style=discord.ButtonStyle.success, custom_id='chat_btn')
    async def chat_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('❌ Não autorizado.', ephemeral=True)
            return
        await interaction.response.send_modal(ChatModal())

    @discord.ui.button(label='🧹 Iniciar', style=discord.ButtonStyle.danger, custom_id='start_btn')
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('❌ Não autorizado.', ephemeral=True)
            return
        data = user_data.get(self.user_id, {})
        if not data.get('token') or not data.get('chat_id'):
            await interaction.response.send_message('❌ Configure token e chat primeiro.', ephemeral=True)
            return
        if data.get('cleaning', False):
            await interaction.response.send_message('⏳ Já está limpando.', ephemeral=True)
            return

        # Iniciar limpeza
        await interaction.response.defer(ephemeral=False)
        progress_msg = await interaction.followup.send('🔄 Iniciando...')
        user_data[self.user_id]['cleaning'] = True
        user_data[self.user_id]['cancel'] = False
        # Executar em background
        bot.loop.create_task(
            self.clean_task(interaction, progress_msg)
        )

    @discord.ui.button(label='⏹️ Cancelar', style=discord.ButtonStyle.secondary, custom_id='cancel_btn')
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('❌ Não autorizado.', ephemeral=True)
            return
        if user_data.get(self.user_id, {}).get('cleaning', False):
            user_data[self.user_id]['cancel'] = True
            await interaction.response.send_message('⏹️ Cancelamento solicitado...', ephemeral=True)
        else:
            await interaction.response.send_message('❌ Nenhuma limpeza em andamento.', ephemeral=True)

    async def clean_task(self, interaction: discord.Interaction, progress_msg: discord.Message):
        user_id = self.user_id
        data = user_data[user_id]
        token = data['token']
        chat_id = data['chat_id']
        headers = {'Authorization': token, 'Content-Type': 'application/json'}

        deleted = 0
        failed = 0
        total_fetched = 0
        last_id = None
        start_time = time.time()
        rate_limit_delay = 0.2
        max_duration = 300  # 5 minutos de limite por segurança

        try:
            async with aiohttp.ClientSession() as session:
                while not data.get('cancel', False):
                    # Verificar tempo máximo
                    if time.time() - start_time > max_duration:
                        await progress_msg.edit(content='⏰ Tempo máximo atingido (5min). Limpeza interrompida.')
                        break

                    url = f'https://discord.com/api/v10/channels/{chat_id}/messages?limit=100'
                    if last_id:
                        url += f'&before={last_id}'
                    async with session.get(url, headers=headers) as resp:
                        if resp.status == 429:
                            retry_after = (await resp.json()).get('retry_after', 1)
                            await progress_msg.edit(content=f'⏳ Rate limit! Aguardando {retry_after:.1f}s...')
                            await asyncio.sleep(retry_after)
                            continue
                        if resp.status != 200:
                            await progress_msg.edit(content=f'❌ Erro {resp.status}')
                            break
                        messages = await resp.json()
                        if not messages:
                            break

                        total_fetched += len(messages)
                        for msg in messages:
                            if data.get('cancel', False):
                                break
                            if msg['author']['id'] == str(user_id):
                                del_url = f'https://discord.com/api/v10/channels/{chat_id}/messages/{msg["id"]}'
                                async with session.delete(del_url, headers=headers) as del_resp:
                                    if del_resp.status == 204:
                                        deleted += 1
                                    elif del_resp.status == 429:
                                        retry_after = (await del_resp.json()).get('retry_after', 1)
                                        await progress_msg.edit(content=f'⏳ Rate limit (delete). Aguardando {retry_after:.1f}s...')
                                        await asyncio.sleep(retry_after)
                                    else:
                                        failed += 1
                                # Pausa adaptativa
                                await asyncio.sleep(rate_limit_delay)

                            # Atualizar progresso a cada 5 mensagens
                            if (deleted + failed) % 5 == 0:
                                await self.update_progress(progress_msg, deleted, failed, total_fetched, start_time)

                        last_id = messages[-1]['id']
                        if len(messages) < 100:
                            break

            # Finalização
            await self.update_progress(progress_msg, deleted, failed, total_fetched, start_time, final=True)
        except Exception as e:
            await progress_msg.edit(content=f'❌ Erro: {e}')
        finally:
            user_data[user_id]['cleaning'] = False
            user_data[user_id]['cancel'] = False

    async def update_progress(self, msg: discord.Message, deleted: int, failed: int, total: int, start_time: float, final=False):
        """Atualiza a mensagem com barra de progresso e estatísticas."""
        elapsed = time.time() - start_time
        # Barra de progresso simples (10 caracteres)
        if total > 0:
            progress = min(1.0, deleted / total)  # aproximado
        else:
            progress = 0.0
        bar_length = 20
        filled = int(bar_length * progress)
        bar = '█' * filled + '░' * (bar_length - filled)
        percent = int(progress * 100)
        status = '✅ CONCLUÍDO' if final else '🔄 EM ANDAMENTO'
        content = f"**{status}**\n" \
                  f"Chat: {user_data[msg.interaction.user.id]['chat_id']}\n" \
                  f"🗑️ Deletadas: {deleted}  |  ❌ Falhas: {failed}\n" \
                  f"📊 Analisadas: {total}\n" \
                  f"⏱️ Tempo: {int(elapsed)}s\n" \
                  f"[{bar}] {percent}%"
        await msg.edit(content=content)

# ============================================================
# COMANDO /paineldm
# ============================================================
@bot.tree.command(name='paineldm', description='Abre o painel de limpeza de DM')
async def paineldm(interaction: discord.Interaction):
    view = PainelView(interaction.user.id)
    embed = discord.Embed(
        title='🛠️ Painel de Limpeza',
        description='Configure token e chat, depois inicie a limpeza.',
        color=discord.Color.blue()
    )
    data = user_data.get(interaction.user.id, {})
    embed.add_field(name='🔑 Token', value='✅ OK' if data.get('token') else '❌ Não configurado', inline=True)
    embed.add_field(name='💬 Chat', value=f'`{data.get("chat_id", "N/A")}`' if data.get('chat_id') else '❌ Não definido', inline=True)
    embed.add_field(name='🧹 Status', value='🔄 Limpando' if data.get('cleaning') else '✅ Parado', inline=True)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

# ============================================================
# EVENTOS
# ============================================================
@bot.event
async def on_ready():
    print(f'✅ Logado como {bot.user}')
    await bot.tree.sync()
    print('✅ Comandos sincronizados.')

# ============================================================
# INICIALIZAÇÃO
# ============================================================
if __name__ == '__main__':
    bot.run(TOKEN_BOT)