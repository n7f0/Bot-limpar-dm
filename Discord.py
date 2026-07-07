import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncio
import os
import random
import time
import math
import json

# ============================================================
# CONFIGURAÇÃO DO BOT OFICIAL
# ============================================================
TOKEN_BOT = os.getenv('BOT_TOKEN') # Ou coloque sua string direta aqui para testes
if not TOKEN_BOT:
    print("❌ Defina a variável de ambiente BOT_TOKEN.")
    exit(1)

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='!', intents=intents)

# ============================================================
# CONFIGURAÇÕES DE SEGURANÇA (AJUSTE AQUI)
# ============================================================
MIN_DELAY = 2.0          
MAX_DELAY = 5.0          
PAUSE_AFTER = 50         
PAUSE_DURATION = 30      
MAX_MESSAGES = 500       

# ============================================================
# ESTRUTURA DE DADOS GLOBAL
# ============================================================
# {user_id: {'token': str, 'chat_id': int, 'cleaning': bool, 'cancel_event': Event, 'farming': bool, 'farm_cancel': Event}}
user_data = {} 

def get_user(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            'token': None, 
            'chat_id': None, 
            'cleaning': False, 
            'cancel_event': None,
            'farming': False,
            'farm_cancel': None
        }
    return user_data[user_id]

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
        data = get_user(interaction.user.id)
        data['token'] = self.token_input.value.strip()
        await interaction.response.send_message('✅ Token configurado com sucesso!', ephemeral=True)

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
            await interaction.response.send_message('❌ ID inválido. Apenas números.', ephemeral=True)
            return

        data = get_user(interaction.user.id)
        token = data.get('token')
        if not token:
            await interaction.response.send_message('❌ Configure o token primeiro.', ephemeral=True)
            return

        headers = {'Authorization': token, 'Content-Type': 'application/json'}
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://discord.com/api/v10/channels/{chat_id}', headers=headers) as resp:
                if resp.status != 200:
                    await interaction.response.send_message('❌ Canal não encontrado ou sem acesso.', ephemeral=True)
                    return
                canal_data = await resp.json()
                if canal_data.get('type') != 1:
                    await interaction.response.send_message('❌ O ID fornecido não é de uma DM.', ephemeral=True)
                    return

        data['chat_id'] = chat_id
        await interaction.response.send_message(f'✅ Chat DM definido: `{chat_id}`', ephemeral=True)

class FarmCallModal(discord.ui.Modal, title='🎧 Configurar Farm de Call'):
    channel_input = discord.ui.TextInput(
        label='ID do Canal de Voz',
        placeholder='Ex: 123456789012345678',
        style=discord.TextStyle.short,
        required=True
    )
    hours_input = discord.ui.TextInput(
        label='Tempo em Horas',
        placeholder='Ex: 5',
        style=discord.TextStyle.short,
        required=True,
        default='1'
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel_id = int(self.channel_input.value.strip())
            hours = float(self.hours_input.value.strip().replace(',', '.'))
        except ValueError:
            await interaction.response.send_message('❌ Valores inválidos. Use apenas números.', ephemeral=True)
            return

        data = get_user(interaction.user.id)
        if data.get('farming'):
            await interaction.response.send_message('⏳ A conta já está farmando em uma call.', ephemeral=True)
            return

        data['farming'] = True
        data['farm_cancel'] = asyncio.Event()

        await interaction.response.defer(ephemeral=False)
        msg = await interaction.followup.send(f'🔄 **Conectando à call...** (Alvo: {hours} horas)')

        bot.loop.create_task(perform_voice_farm(interaction.user.id, channel_id, hours, msg))

# ============================================================
# LÓGICA DE WEBSOCKET (VOICE FARM)
# ============================================================
async def perform_voice_farm(user_id, channel_id, hours, progress_msg):
    data = get_user(user_id)
    token = data.get('token')
    cancel_event = data['farm_cancel']
    
    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    
    async with aiohttp.ClientSession() as session:
        # 1. Descobrir o guild_id (Servidor) do canal de voz
        guild_id = None
        async with session.get(f'https://discord.com/api/v10/channels/{channel_id}', headers=headers) as resp:
            if resp.status == 200:
                channel_data = await resp.json()
                guild_id = channel_data.get('guild_id')
            else:
                await progress_msg.edit(content='❌ Erro: Não foi possível acessar o canal de voz. Verifique o ID e o Token.')
                data['farming'] = False
                return

        await progress_msg.edit(content='🔄 **Autenticando no Gateway do Discord...**')
        
        # 2. Conectar ao Gateway para manter o status online e na call
        ws_url = 'wss://gateway.discord.gg/?v=10&encoding=json'
        try:
            async with session.ws_connect(ws_url) as ws:
                hello_msg = await ws.receive_json()
                heartbeat_interval = hello_msg['d']['heartbeat_interval'] / 1000.0

                # Payload de Identificação
                await ws.send_json({
                    "op": 2,
                    "d": {
                        "token": token,
                        "properties": {"os": "Windows", "browser": "Chrome", "device": "PC"}
                    }
                })
                
                await asyncio.sleep(2) # Aguarda autenticação

                # Payload de Voice State Update (Entrar na call mutado)
                await ws.send_json({
                    "op": 4,
                    "d": {
                        "guild_id": guild_id,
                        "channel_id": str(channel_id),
                        "self_mute": True,
                        "self_deaf": True
                    }
                })

                end_time = time.time() + (hours * 3600)
                next_heartbeat = time.time() + heartbeat_interval
                
                await progress_msg.edit(content=f'✅ **Conta conectada na Call!**\n⏳ Tempo programado: `{hours} horas`\n🎧 Canal ID: `{channel_id}`')

                # Loop para manter a conexão viva (Heartbeat)
                while time.time() < end_time and not cancel_event.is_set():
                    timeout = max(0.5, next_heartbeat - time.time())
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=timeout)
                        if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
                    except asyncio.TimeoutError:
                        # Enviar Heartbeat
                        await ws.send_json({"op": 1, "d": None})
                        next_heartbeat = time.time() + heartbeat_interval
                    except Exception:
                        break

        except Exception as e:
            await progress_msg.edit(content=f'❌ Ocorreu um erro no Gateway: `{str(e)}`')
            data['farming'] = False
            return

    if cancel_event.is_set():
        await progress_msg.edit(content='⏹️ **Farm de call interrompido pelo usuário.**')
    else:
        await progress_msg.edit(content='✅ **Farm de call finalizado (Tempo esgotado).**')
    
    data['farming'] = False

# ============================================================
# VIEWS (MENUS)
# ============================================================
class CallView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label='▶️ Entrar Call', style=discord.ButtonStyle.success)
    async def enter_call(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message('❌ Privado.', ephemeral=True)
        
        data = get_user(self.user_id)
        if not data.get('token'):
            return await interaction.response.send_message('❌ Configure o token primeiro no menu principal.', ephemeral=True)
            
        await interaction.response.send_modal(FarmCallModal())

    @discord.ui.button(label='⏹️ Sair da Call', style=discord.ButtonStyle.danger)
    async def leave_call(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message('❌ Privado.', ephemeral=True)
            
        data = get_user(self.user_id)
        if not data.get('farming'):
            return await interaction.response.send_message('❌ A conta não está farmando no momento.', ephemeral=True)
            
        if data.get('farm_cancel'):
            data['farm_cancel'].set()
            await interaction.response.send_message('⏹️ Desconectando da call...', ephemeral=True)

    @discord.ui.button(label='⬅️ Voltar', style=discord.ButtonStyle.secondary)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return
        await interaction.response.edit_message(view=PainelView(self.user_id))

class PainelView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label='🔑 Token', style=discord.ButtonStyle.primary, row=0)
    async def token_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.send_modal(TokenModal())

    @discord.ui.button(label='💬 Chat DM', style=discord.ButtonStyle.success, row=0)
    async def chat_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.send_modal(ChatModal())

    @discord.ui.button(label='📊 Servidores', style=discord.ButtonStyle.secondary, row=0)
    async def servers_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        data = get_user(self.user_id)
        token = data.get('token')
        
        if not token:
            return await interaction.response.send_message('❌ Configure o token primeiro.', ephemeral=True)

        await interaction.response.defer(ephemeral=False)
        headers = {'Authorization': token}
        
        async with aiohttp.ClientSession() as session:
            # Puxar servidores
            async with session.get('https://discord.com/api/v10/users/@me/guilds', headers=headers) as resp:
                if resp.status != 200:
                    return await interaction.followup.send('❌ Erro ao buscar servidores. Token inválido?')
                guilds = await resp.json()

            total_guilds = len(guilds)
            embed = discord.Embed(title=f'📊 Análise de Servidores ({total_guilds} encontrados)', color=discord.Color.purple())
            embed.description = "⚠️ Verificando histórico apenas nos 5 primeiros servidores para evitar ban do Discord (Rate Limit)."
            
            # Verificar mensagens nos top 5 servidores
            for guild in guilds[:5]:
                guild_id = guild['id']
                guild_name = guild['name']
                
                # Busca rápida de mensagens do autor no servidor
                search_url = f'https://discord.com/api/v9/guilds/{guild_id}/messages/search?author_id={self.user_id}'
                async with session.get(search_url, headers=headers) as s_resp:
                    if s_resp.status == 200:
                        s_data = await s_resp.json()
                        total_msgs = s_data.get('total_results', 0)
                        status = f"✅ Mandou mensagem ({total_msgs}+)" if total_msgs > 0 else "❌ Sem mensagens recentes"
                    else:
                        status = "⚠️ Sem permissão para ler histórico"
                        
                embed.add_field(name=guild_name, value=status, inline=False)
                await asyncio.sleep(1) # Delay de segurança
                
        await interaction.followup.send(embed=embed)

    @discord.ui.button(label='🧹 Limpar DM', style=discord.ButtonStyle.danger, row=1)
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        data = get_user(self.user_id)
        if not data.get('token') or not data.get('chat_id'):
            return await interaction.response.send_message('❌ Configure token e chat primeiro.', ephemeral=True)
        if data.get('cleaning'):
            return await interaction.response.send_message('⏳ Limpeza já em andamento.', ephemeral=True)

        data['cleaning'] = True
        data['cancel_event'] = asyncio.Event()

        await interaction.response.defer(ephemeral=False)
        progress_msg = await interaction.followup.send('🔄 **Preparando a limpeza...**')
        bot.loop.create_task(self.perform_cleanup(interaction, data['token'], data['chat_id'], progress_msg))

    @discord.ui.button(label='⏹️ Parar Limpeza', style=discord.ButtonStyle.secondary, row=1)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        data = get_user(self.user_id)
        if not data.get('cleaning'):
            return await interaction.response.send_message('❌ Nenhuma limpeza em andamento.', ephemeral=True)
        if data.get('cancel_event'):
            data['cancel_event'].set()
            await interaction.response.send_message('⏹️ Interrompendo a limpeza...', ephemeral=True)

    @discord.ui.button(label='🎧 Call (Farm)', style=discord.ButtonStyle.primary, row=1)
    async def call_menu_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id: return
        await interaction.response.edit_message(view=CallView(self.user_id))

    async def perform_cleanup(self, interaction, token, chat_id, progress_msg):
        user_id = self.user_id
        data = get_user(user_id)
        cancel_event = data['cancel_event']
        headers = {'Authorization': token, 'Content-Type': 'application/json'}

        messages_deleted, total_fetched = 0, 0
        last_id = None
        start_time = time.time()
        delay = random.uniform(MIN_DELAY, MAX_DELAY)
        paused = False

        async with aiohttp.ClientSession() as session:
            while True:
                if cancel_event and cancel_event.is_set():
                    await progress_msg.edit(content='⏹️ **Limpeza cancelada pelo usuário.**')
                    break

                if messages_deleted > 0 and messages_deleted % PAUSE_AFTER == 0 and not paused:
                    paused = True
                    await progress_msg.edit(content=f'⏸️ **Pausa programada** (30s). Aguarde...')
                    await asyncio.sleep(PAUSE_DURATION)
                    paused = False

                url = f'https://discord.com/api/v10/channels/{chat_id}/messages?limit=100'
                if last_id: url += f'&before={last_id}'
                
                try:
                    async with session.get(url, headers=headers) as resp:
                        if resp.status == 429:
                            retry = float(resp.headers.get('Retry-After', 5))
                            await asyncio.sleep(retry)
                            continue
                        if resp.status != 200:
                            await progress_msg.edit(content=f'❌ Erro {resp.status} ao buscar mensagens.')
                            break
                        messages = await resp.json()
                        if not messages: break
                except Exception as e:
                    await progress_msg.edit(content=f'❌ Erro de conexão: {e}')
                    break

                total_fetched += len(messages)
                
                for msg in messages:
                    if cancel_event and cancel_event.is_set(): break
                    
                    if msg['author']['id'] == str(user_id):
                        del_url = f'https://discord.com/api/v10/channels/{chat_id}/messages/{msg["id"]}'
                        try:
                            async with session.delete(del_url, headers=headers) as del_resp:
                                if del_resp.status == 429:
                                    retry = float(del_resp.headers.get('Retry-After', 5))
                                    await asyncio.sleep(retry)
                                    continue
                                if del_resp.status == 204:
                                    messages_deleted += 1
                        except Exception:
                            pass

                        await asyncio.sleep(delay)

                    if messages_deleted % 3 == 0 and messages_deleted > 0:
                        await self.update_progress(progress_msg, messages_deleted, total_fetched, MAX_MESSAGES, start_time, delay)

                    if messages_deleted >= MAX_MESSAGES:
                        await progress_msg.edit(content=f'⚠️ **Limite de segurança atingido** ({MAX_MESSAGES} mensagens).')
                        data['cleaning'] = False
                        return

                last_id = messages[-1]['id']
                if len(messages) < 100: break

        elapsed = time.time() - start_time
        await progress_msg.edit(
            content=f'✅ **Limpeza concluída!**\n🗑️ `{messages_deleted}` deletadas\n📊 `{total_fetched}` analisadas\n⏱️ `{elapsed:.1f}s` totais.'
        )
        data['cleaning'] = False

    async def update_progress(self, msg, deleted, fetched, max_msgs, start_time, current_delay):
        percent = min(100, int((deleted / max_msgs) * 100))
        bar_len = 15
        filled = int(bar_len * percent / 100)
        bar = '🟦' * filled + '⬛' * (bar_len - filled)
        elapsed = time.time() - start_time

        if deleted > 0:
            remaining = max_msgs - deleted
            eta = time.strftime('%H:%M:%S', time.gmtime(remaining * current_delay * 1.1))
        else:
            eta = 'Calculando...'

        await msg.edit(
            content=f'🔄 **Limpando as Mensagens...**\n\n'
                    f'{bar} **{percent}%**\n'
                    f'🗑️ **Deletadas:** `{deleted}/{max_msgs}`\n'
                    f'📊 **Analisadas:** `{fetched}`\n'
                    f'⏳ **ETA (Restante):** `{eta}`'
        )

# ============================================================
# COMANDO /paineldm
# ============================================================
@bot.tree.command(name='paineldm', description='Abre o painel de controle do Self-Bot')
async def paineldm(interaction: discord.Interaction):
    view = PainelView(interaction.user.id)
    embed = discord.Embed(
        title='🛠️ Centro de Controle de Contas (Self)',
        description='Painel seguro para gerenciar sua conta, limpar DMs e farmar em calls.',
        color=discord.Color.dark_theme()
    )
    embed.add_field(name='📝 Instruções', value='1. Configure o seu Token primeiro.\n2. Defina o ID do Chat/Call.\n3. Inicie o processo desejado.', inline=False)
    embed.set_footer(text='⚠️ O uso de Self-Bots/Tokens de usuário é contra os Termos de Serviço do Discord. Use por sua conta e risco.')

    await interaction.response.send_message(embed=embed, view=view, ephemeral=False)

# ============================================================
# INICIALIZAÇÃO
# ============================================================
@bot.event
async def on_ready():
    print(f'✅ Bot conectado perfeitamente como {bot.user}')
    await bot.tree.sync()
    print('📌 Comandos Slash Sincronizados.')

if __name__ == "__main__":
    bot.run(TOKEN_BOT)
