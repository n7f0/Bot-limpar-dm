import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import asyncio
import os
import random
import time
import io
import base64

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
# CONFIGURAÇÕES DE SEGURANÇA MÁXIMA (ANTI-BAN)
# ============================================================
MIN_DELAY = 15.0         # Mínimo de 15s entre deleções
MAX_DELAY = 35.0         # Máximo de 35s entre deleções
PAUSE_AFTER = 20         # Pausa longa a cada 20 mensagens apagadas
PAUSE_DUR_MIN = 120.0    # Mínimo da pausa longa (2 minutos)
PAUSE_DUR_MAX = 180.0    # Máximo da pausa longa (3 minutos)
MAX_MESSAGES = 150       # Limite diário recomendado por execução
MAX_BACKUP = 3000        # Limite máximo de mensagens lidas no backup

# ============================================================
# ESTRUTURA DE DADOS GLOBAL
# ============================================================
user_data = {} 

def get_user(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            'token': None, 'chat_id': None, 'cleaning': False, 
            'clean_cancel': None, 'farming_call': False,
            'call_cancel': None, 'auto_farming': False, 'farm_cancel': None
        }
    return user_data[user_id]

# ============================================================
# MODAIS (ENTRADA DE DADOS)
# ============================================================
class TokenModal(discord.ui.Modal, title='🔑 Configurar Token do Usuário'):
    token_input = discord.ui.TextInput(label='Token de usuário', style=discord.TextStyle.paragraph, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        get_user(interaction.user.id)['token'] = self.token_input.value.strip()
        await interaction.response.send_message('✅ Token configurado com sucesso!', ephemeral=True)

class ChatModal(discord.ui.Modal, title='💬 Definir Chat (DM ou Servidor)'):
    chat_input = discord.ui.TextInput(label='ID do Canal/DM', style=discord.TextStyle.short, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        try: chat_id = int(self.chat_input.value.strip())
        except ValueError: return await interaction.response.send_message('❌ ID inválido. Apenas números.', ephemeral=True)

        data = get_user(interaction.user.id)
        if not data.get('token'): return await interaction.response.send_message('❌ Configure o token primeiro.', ephemeral=True)

        headers = {'Authorization': data['token'], 'Content-Type': 'application/json'}
        async with aiohttp.ClientSession() as session:
            async with session.get(f'https://discord.com/api/v10/channels/{chat_id}', headers=headers) as resp:
                if resp.status != 200:
                    return await interaction.response.send_message('❌ Canal não encontrado ou sem permissão de leitura.', ephemeral=True)

        data['chat_id'] = chat_id
        await interaction.response.send_message(f'✅ Chat alvo definido: `{chat_id}`', ephemeral=True)

class ScheduleModal(discord.ui.Modal, title='⏰ Agendar Mensagem'):
    msg_input = discord.ui.TextInput(label='Mensagem a ser enviada', style=discord.TextStyle.paragraph, required=True)
    delay_input = discord.ui.TextInput(label='Daqui a quantos minutos?', style=discord.TextStyle.short, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try: delay_min = float(self.delay_input.value.strip().replace(',', '.'))
        except ValueError: return await interaction.response.send_message('❌ Tempo inválido.', ephemeral=True)
        
        if delay_min < 1: return await interaction.response.send_message('❌ O tempo mínimo é de 1 minuto.', ephemeral=True)

        data = get_user(interaction.user.id)
        bot.loop.create_task(perform_schedule(data['token'], data['chat_id'], self.msg_input.value, delay_min * 60))
        await interaction.response.send_message(f'✅ Mensagem agendada para daqui a {delay_min} minutos.', ephemeral=True)

class FarmBumperModal(discord.ui.Modal, title='🔄 Auto-Farm (Seguro)'):
    cmd_input = discord.ui.TextInput(label='Comando/Mensagem (Ex: !bump)', style=discord.TextStyle.short, required=True)
    interval_input = discord.ui.TextInput(label='Minutos (Mín: 15)', style=discord.TextStyle.short, default='120', required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try: interval_min = float(self.interval_input.value.strip().replace(',', '.'))
        except ValueError: return await interaction.response.send_message('❌ Intervalo inválido.', ephemeral=True)

        if interval_min < 15:
            return await interaction.response.send_message('🛡️ **Anti-Ban:** Para sua segurança, o intervalo mínimo permitido é de 15 minutos.', ephemeral=True)

        data = get_user(interaction.user.id)
        data['auto_farming'] = True
        data['farm_cancel'] = asyncio.Event()

        await interaction.response.send_message(f'✅ Auto-Farm furtivo iniciado. Envio a cada {interval_min} min.', ephemeral=True)
        bot.loop.create_task(perform_auto_farm(interaction.user.id, self.cmd_input.value, interval_min * 60))

class CloneModal(discord.ui.Modal, title='🎭 Clonar Perfil'):
    target_input = discord.ui.TextInput(label='ID do Usuário Alvo', style=discord.TextStyle.short, required=True)
    async def on_submit(self, interaction: discord.Interaction):
        try: target_id = int(self.target_input.value.strip())
        except ValueError: return await interaction.response.send_message('❌ ID inválido.', ephemeral=True)

        await interaction.response.defer(ephemeral=False)
        msg = await interaction.followup.send('🔄 **Lendo dados do perfil com segurança...**')
        bot.loop.create_task(perform_clone(interaction.user.id, target_id, msg))

class CallModal(discord.ui.Modal, title='🎧 Entrar em Call'):
    channel_input = discord.ui.TextInput(label='ID do Canal de Voz', style=discord.TextStyle.short, required=True)
    hours_input = discord.ui.TextInput(label='Tempo (Horas)', style=discord.TextStyle.short, default='2', required=True)
    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel_id = int(self.channel_input.value)
            hours = float(self.hours_input.value.replace(',', '.'))
        except: return await interaction.response.send_message('❌ Valores inválidos.', ephemeral=True)

        data = get_user(interaction.user.id)
        data['farming_call'] = True
        data['call_cancel'] = asyncio.Event()

        await interaction.response.defer()
        msg = await interaction.followup.send(f'🔄 **Negociando conexão com o Gateway...**')
        bot.loop.create_task(perform_voice_farm(interaction.user.id, channel_id, hours, msg))

# ============================================================
# FUNÇÕES CORE (AUTOMATIZAÇÕES FURTIVAS)
# ============================================================
async def perform_schedule(token, chat_id, message, delay_sec):
    await asyncio.sleep(delay_sec)
    async with aiohttp.ClientSession() as session:
        await session.post(
            f'https://discord.com/api/v10/channels/{chat_id}/messages',
            headers={'Authorization': token, 'Content-Type': 'application/json'},
            json={'content': message}
        )

async def perform_auto_farm(user_id, message, interval_sec):
    data = get_user(user_id)
    headers = {'Authorization': data['token'], 'Content-Type': 'application/json'}
    
    async with aiohttp.ClientSession() as session:
        while data['auto_farming'] and not data['farm_cancel'].is_set():
            try:
                await session.post(f'https://discord.com/api/v10/channels/{data["chat_id"]}/messages', headers=headers, json={'content': message})
            except: pass
            
            # Divide a espera para verificar cancelamento rápido e adiciona randomização (+- 30s)
            real_interval = interval_sec + random.uniform(-30, 30)
            for _ in range(int(real_interval / 5)):
                if data['farm_cancel'].is_set(): break
                await asyncio.sleep(5)

async def perform_backup(interaction: discord.Interaction, token, chat_id):
    headers = {'Authorization': token}
    last_id = None
    messages_str = []
    
    await interaction.response.defer(ephemeral=False)
    prog_msg = await interaction.followup.send(f'🔄 **Backup Stealth Iniciado.** \nLimite configurado: {MAX_BACKUP} msgs. Isso leva tempo para imitar um humano lendo...')
    
    async with aiohttp.ClientSession() as session:
        while len(messages_str) < MAX_BACKUP:
            url = f'https://discord.com/api/v10/channels/{chat_id}/messages?limit=100'
            if last_id: url += f'&before={last_id}'
            
            async with session.get(url, headers=headers) as resp:
                if resp.status == 429:
                    await asyncio.sleep(float(resp.headers.get('Retry-After', 5)) + 2)
                    continue
                if resp.status != 200: break
                
                msgs = await resp.json()
                if not msgs: break
                
                for m in msgs:
                    author = m['author']['username']
                    content = m.get('content', '[Vazio ou Anexo]')
                    timestamp = m['timestamp']
                    messages_str.append(f"[{timestamp}] {author}: {content}")
                
                last_id = msgs[-1]['id']
                
                # Jitter massivo para evitar flags de scraping
                delay_rolagem = random.uniform(4.0, 8.0)
                await asyncio.sleep(delay_rolagem) 
                
    if not messages_str:
        return await prog_msg.edit(content='❌ Nenhuma mensagem encontrada ou sem acesso.')

    messages_str.reverse()
    file_content = "\n".join(messages_str)
    buffer = io.BytesIO(file_content.encode('utf-8'))
    
    await prog_msg.edit(content=f'✅ **Backup Concluído com Segurança!**\nForam lidas {len(messages_str)} mensagens.')
    await interaction.followup.send(file=discord.File(buffer, filename=f"backup_chat_{chat_id}.txt"))

async def perform_clone(user_id, target_id, progress_msg):
    data = get_user(user_id)
    headers = {'Authorization': data['token']}
    
    async with aiohttp.ClientSession() as session:
        async with session.get(f'https://discord.com/api/v10/users/{target_id}', headers=headers) as resp:
            if resp.status != 200:
                return await progress_msg.edit(content='❌ Usuário alvo não encontrado.')
            target_data = await resp.json()

        payload = {}
        if 'bio' in target_data:
            payload['bio'] = target_data['bio']

        if target_data.get('avatar'):
            av_hash = target_data['avatar']
            av_url = f"https://cdn.discordapp.com/avatars/{target_id}/{av_hash}.png?size=1024"
            async with session.get(av_url) as av_resp:
                if av_resp.status == 200:
                    av_bytes = await av_resp.read()
                    av_b64 = base64.b64encode(av_bytes).decode('utf-8')
                    payload['avatar'] = f"data:image/png;base64,{av_b64}"

        # Delay de segurança antes de aplicar a mudança na conta
        await asyncio.sleep(random.uniform(2.0, 4.0))

        if payload:
            async with session.patch('https://discord.com/api/v10/users/@me', headers=headers, json=payload) as patch_resp:
                if patch_resp.status == 200:
                    await progress_msg.edit(content='✅ **Perfil clonado com sucesso!**')
                else:
                    await progress_msg.edit(content=f'❌ Erro ao atualizar perfil: {patch_resp.status}')
        else:
            await progress_msg.edit(content='⚠️ O alvo não tem avatar ou bio configurada.')

async def perform_cleanup(interaction, token, chat_id, progress_msg):
    data = get_user(interaction.user.id)
    headers = {'Authorization': token, 'Content-Type': 'application/json'}
    messages_deleted, total_fetched = 0, 0
    last_id = None
    start_time = time.time()

    async with aiohttp.ClientSession() as session:
        while True:
            if data['clean_cancel'] and data['clean_cancel'].is_set():
                break

            url = f'https://discord.com/api/v10/channels/{chat_id}/messages?limit=100'
            if last_id: url += f'&before={last_id}'
            
            async with session.get(url, headers=headers) as resp:
                if resp.status == 429:
                    await asyncio.sleep(float(resp.headers.get('Retry-After', 5)) + random.uniform(1.0, 3.0))
                    continue
                if resp.status != 200: break
                messages = await resp.json()
                if not messages: break

            total_fetched += len(messages)
            
            for msg in messages:
                if data['clean_cancel'].is_set(): break
                
                # Identifica se a mensagem é do dono do token
                if msg['author']['id'] == str(interaction.user.id):
                    del_url = f'https://discord.com/api/v10/channels/{chat_id}/messages/{msg["id"]}'
                    try:
                        async with session.delete(del_url, headers=headers) as del_resp:
                            if del_resp.status == 429:
                                await asyncio.sleep(float(del_resp.headers.get('Retry-After', 5)))
                                continue
                            if del_resp.status == 204: 
                                messages_deleted += 1
                                
                                # Pausa de fadiga humana
                                if messages_deleted % PAUSE_AFTER == 0:
                                    pausa = random.uniform(PAUSE_DUR_MIN, PAUSE_DUR_MAX)
                                    await progress_msg.edit(content=f'⏸️ **Simulando inatividade humana...**\nPausa de `{int(pausa)}` segundos.')
                                    await asyncio.sleep(pausa)
                                
                                # Atualiza status a cada 3 msgs
                                elif messages_deleted % 3 == 0:
                                    await progress_msg.edit(content=f'🔄 **Limpando de forma furtiva...**\n🗑️ Deletadas: `{messages_deleted}/{MAX_MESSAGES}`')

                    except: pass
                    
                    # Delay humano aleatório entre cada deleção
                    await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

                if messages_deleted >= MAX_MESSAGES:
                    data['cleaning'] = False
                    return await progress_msg.edit(content=f'✅ **Cota diária segura atingida** ({MAX_MESSAGES}). Parando para evitar ban.')

            last_id = messages[-1]['id']
            if len(messages) < 100: break

    data['cleaning'] = False
    await progress_msg.edit(content=f'✅ **Limpeza Furtiva Concluída!**\n🗑️ `{messages_deleted}` mensagens apagadas com sucesso.\n⏱️ Tempo rodando: `{int(time.time() - start_time)}` segundos.')

async def perform_voice_farm(user_id, channel_id, hours, progress_msg):
    data = get_user(user_id)
    token = data['token']
    headers = {'Authorization': token}
    
    async with aiohttp.ClientSession() as session:
        guild_id = None
        async with session.get(f'https://discord.com/api/v10/channels/{channel_id}', headers=headers) as resp:
            if resp.status == 200: guild_id = (await resp.json()).get('guild_id')
            else: return await progress_msg.edit(content='❌ Erro ao acessar o canal. Verifique permissões.')

        try:
            async with session.ws_connect('wss://gateway.discord.gg/?v=10&encoding=json') as ws:
                hello = await ws.receive_json()
                interval = hello['d']['heartbeat_interval'] / 1000.0

                # Identifica-se como cliente de navegador real
                await ws.send_json({"op": 2, "d": {"token": token, "properties": {"os": "Windows", "browser": "Discord Client", "device": "Windows"}}})
                await asyncio.sleep(random.uniform(2.0, 4.0))
                await ws.send_json({"op": 4, "d": {"guild_id": guild_id, "channel_id": str(channel_id), "self_mute": True, "self_deaf": True}})

                end_time = time.time() + (hours * 3600)
                next_hb = time.time() + interval
                await progress_msg.edit(content=f'✅ **Conta conectada na Call furtivamente!**\n⏰ Permanência: `{hours}h`')

                while time.time() < end_time and not data['call_cancel'].is_set():
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=max(0.5, next_hb - time.time()))
                        if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR): break
                    except asyncio.TimeoutError:
                        await ws.send_json({"op": 1, "d": None})
                        next_hb = time.time() + interval
        except: pass

    data['farming_call'] = False
    await progress_msg.edit(content='⏹️ **Sessão de Call encerrada ou tempo expirado.**')

# ============================================================
# MENUS (VIEWS)
# ============================================================
class PainelPrincipal(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=None)
        self.user_id = user_id

    async def check(self, interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message('❌ Acesso restrito ao dono.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='🔑 Token', style=discord.ButtonStyle.primary, row=0)
    async def btn_token(self, i: discord.Interaction, b: discord.ui.Button):
        if await self.check(i): await i.response.send_modal(TokenModal())

    @discord.ui.button(label='💬 Set Chat / DM', style=discord.ButtonStyle.success, row=0)
    async def btn_chat(self, i: discord.Interaction, b: discord.ui.Button):
        if await self.check(i): await i.response.send_modal(ChatModal())

    @discord.ui.button(label='💾 Backup Stealth', style=discord.ButtonStyle.secondary, row=0)
    async def btn_backup(self, i: discord.Interaction, b: discord.ui.Button):
        if not await self.check(i): return
        data = get_user(self.user_id)
        if not data['token'] or not data['chat_id']: return await i.response.send_message('❌ Defina Token e Chat primeiro.', ephemeral=True)
        bot.loop.create_task(perform_backup(i, data['token'], data['chat_id']))

    @discord.ui.button(label='🧹 Limpar Furtivo', style=discord.ButtonStyle.danger, row=1)
    async def btn_clean(self, i: discord.Interaction, b: discord.ui.Button):
        if not await self.check(i): return
        data = get_user(self.user_id)
        if not data['token'] or not data['chat_id']: return await i.response.send_message('❌ Defina Token e Chat.', ephemeral=True)
        if data['cleaning']: return await i.response.send_message('⏳ Já em execução.', ephemeral=True)
        data['cleaning'] = True
        data['clean_cancel'] = asyncio.Event()
        await i.response.defer()
        msg = await i.followup.send('🔄 **Iniciando limpeza humana simulada...**')
        bot.loop.create_task(perform_cleanup(i, data['token'], data['chat_id'], msg))

    @discord.ui.button(label='⏹️ Parar Limpeza', style=discord.ButtonStyle.secondary, row=1)
    async def btn_stop_clean(self, i: discord.Interaction, b: discord.ui.Button):
        if await self.check(i):
            data = get_user(self.user_id)
            if data['clean_cancel']: data['clean_cancel'].set()
            await i.response.send_message('⏹️ Abortando a limpeza...', ephemeral=True)

    @discord.ui.button(label='⏰ Agendar', style=discord.ButtonStyle.primary, row=2)
    async def btn_schedule(self, i: discord.Interaction, b: discord.ui.Button):
        if not await self.check(i): return
        if not get_user(self.user_id)['chat_id']: return await i.response.send_message('❌ Defina Chat Alvo.', ephemeral=True)
        await i.response.send_modal(ScheduleModal())

    @discord.ui.button(label='🔄 Auto-Farm', style=discord.ButtonStyle.success, row=2)
    async def btn_farm(self, i: discord.Interaction, b: discord.ui.Button):
        if not await self.check(i): return
        if not get_user(self.user_id)['chat_id']: return await i.response.send_message('❌ Defina Chat Alvo.', ephemeral=True)
        await i.response.send_modal(FarmBumperModal())

    @discord.ui.button(label='⏹️ Parar Farm', style=discord.ButtonStyle.secondary, row=2)
    async def btn_stop_farm(self, i: discord.Interaction, b: discord.ui.Button):
        if await self.check(i):
            data = get_user(self.user_id)
            data['auto_farming'] = False
            if data['farm_cancel']: data['farm_cancel'].set()
            await i.response.send_message('⏹️ Farm interrompido.', ephemeral=True)

    @discord.ui.button(label='🎭 Clonar Perfil', style=discord.ButtonStyle.primary, row=3)
    async def btn_clone(self, i: discord.Interaction, b: discord.ui.Button):
        if not await self.check(i): return
        if not get_user(self.user_id)['token']: return await i.response.send_message('❌ Defina o Token.', ephemeral=True)
        await i.response.send_modal(CloneModal())

    @discord.ui.button(label='🎧 Entrar Call', style=discord.ButtonStyle.success, row=3)
    async def btn_call(self, i: discord.Interaction, b: discord.ui.Button):
        if not await self.check(i): return
        if not get_user(self.user_id)['token']: return await i.response.send_message('❌ Defina o Token.', ephemeral=True)
        await i.response.send_modal(CallModal())

    @discord.ui.button(label='⏹️ Sair Call', style=discord.ButtonStyle.danger, row=3)
    async def btn_stop_call(self, i: discord.Interaction, b: discord.ui.Button):
        if await self.check(i):
            data = get_user(self.user_id)
            if data['call_cancel']: data['call_cancel'].set()
            await i.response.send_message('⏹️ Desconectando...', ephemeral=True)

# ============================================================
# COMANDO PRINCIPAL
# ============================================================
@bot.tree.command(name='paineldm', description='Abre a suíte avançada com parâmetros de segurança anti-ban.')
async def paineldm(interaction: discord.Interaction):
    embed = discord.Embed(
        title='🛡️ Master Panel - Modo Furtivo',
        description='O sistema agora opera simulando latência e fadiga humana para evitar verificações automáticas do Discord.',
        color=discord.Color.brand_green()
    )
    embed.add_field(name='🧹 Limpeza Segura', value=f'Delay: `{int(MIN_DELAY)}` a `{int(MAX_DELAY)}` segundos.\nCota Máxima: `{MAX_MESSAGES}` msgs/sessão.', inline=False)
    embed.add_field(name='💾 Backup Humanizado', value=f'Limite rígido de leitura estipulado em `{MAX_BACKUP}` mensagens.', inline=False)
    
    await interaction.response.send_message(embed=embed, view=PainelPrincipal(interaction.user.id), ephemeral=False)

@bot.event
async def on_ready():
    print(f'✅ Bot Mestre [Modo Furtivo] operando como {bot.user}')
    await bot.tree.sync()

if __name__ == "__main__":
    bot.run(TOKEN_BOT)
