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
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Dicionário para armazenar tokens por usuário (em memória)
user_tokens = {}

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
        # Salva o token associado ao ID do usuário
        user_tokens[interaction.user.id] = token
        await interaction.response.send_message(
            f'✅ Token configurado com sucesso, {interaction.user.mention}! Agora use `/limpar_dm <ID_DO_CANAL>`.',
            ephemeral=True
        )
        print(f'Token configurado para usuário {interaction.user} (ID: {interaction.user.id})')

# ============================================================
# COMANDOS SLASH
# ============================================================
@bot.tree.command(name='configurar', description='Configura o token do seu usuário para o bot usar')
async def configurar(interaction: discord.Interaction):
    """Abre um modal para inserir o token."""
    await interaction.response.send_modal(TokenModal())

@bot.tree.command(name='limpar_dm', description='Apaga suas mensagens em uma DM')
@app_commands.describe(channel_id='ID do canal privado (DM) que você quer limpar')
async def limpar_dm(interaction: discord.Interaction, channel_id: str):
    """Usa o token armazenado para deletar mensagens suas na DM."""
    user_id = interaction.user.id
    token = user_tokens.get(user_id)
    if not token:
        await interaction.response.send_message(
            '❌ Você ainda não configurou seu token. Use `/configurar` primeiro.',
            ephemeral=True
        )
        return

    # Validar se o ID é numérico
    try:
        channel_id_int = int(channel_id)
    except ValueError:
        await interaction.response.send_message('❌ O ID do canal deve ser um número.', ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)  # Defer para não expirar

    # Fazer requisições à API do Discord usando o token do usuário
    headers = {
        'Authorization': token,
        'Content-Type': 'application/json'
    }
    async with aiohttp.ClientSession() as session:
        # Verificar se o canal existe e é uma DM
        async with session.get(f'https://discord.com/api/v10/channels/{channel_id_int}', headers=headers) as resp:
            if resp.status != 200:
                await interaction.followup.send(
                    '❌ Canal não encontrado ou você não tem acesso. Verifique o ID e se é uma DM.',
                    ephemeral=True
                )
                return
            channel_data = await resp.json()
            if channel_data.get('type') != 1:  # 1 = DM
                await interaction.followup.send('❌ O ID fornecido não é uma DM privada.', ephemeral=True)
                return

        # Buscar mensagens do canal (últimas 1000)
        messages_deleted = 0
        limit = 1000
        last_id = None
        while True:
            url = f'https://discord.com/api/v10/channels/{channel_id_int}/messages?limit=100'
            if last_id:
                url += f'&before={last_id}'
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    await interaction.followup.send(f'❌ Erro ao buscar mensagens: {resp.status}', ephemeral=True)
                    return
                messages = await resp.json()
                if not messages:
                    break
                # Filtrar mensagens do próprio usuário
                for msg in messages:
                    if msg['author']['id'] == str(user_id):
                        # Deletar
                        del_url = f'https://discord.com/api/v10/channels/{channel_id_int}/messages/{msg["id"]}'
                        async with session.delete(del_url, headers=headers) as del_resp:
                            if del_resp.status == 204:
                                messages_deleted += 1
                            else:
                                print(f'Falha ao deletar msg {msg["id"]}: {del_resp.status}')
                        # Pequena pausa para evitar rate-limit
                        await asyncio.sleep(0.1)
                last_id = messages[-1]['id']
                if len(messages) < 100:
                    break

        await interaction.followup.send(
            f'✅ Deletadas {messages_deleted} mensagens suas na DM.',
            ephemeral=True
        )

# ============================================================
# EVENTO DE PRONTO E SINCRONIZAÇÃO DE COMANDOS
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