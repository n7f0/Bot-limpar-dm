import discord
from discord.ext import commands
import os
import sys
import asyncio

# ============================================================
# 1. INSERIR TOKEN (via terminal ou variável de ambiente)
# ============================================================

# Opção 1: Variável de ambiente (recomendado para Railway)
TOKEN = os.getenv('SEU_TOKEN_DE_USUARIO')

# Opção 2: Input no terminal (se não tiver variável de ambiente)
if not TOKEN:
    TOKEN = input("🔑 Cole seu token do Discord e pressione Enter: ").strip()

if not TOKEN:
    print("❌ Token vazio. Encerrando.")
    sys.exit(1)

# ============================================================
# 2. CONFIGURAR O BOT (self-bot)
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix='!', self_bot=True, intents=intents)

# Variável para guardar o ID do canal DM alvo
canal_alvo_id = None

@bot.event
async def on_ready():
    print(f'✅ Logado como {bot.user} (ID: {bot.user.id})')
    print('📌 Comandos disponíveis:')
    print('   !definir_dm <ID_DO_CANAL>  - Define qual DM será limpa')
    print('   !limpar                   - Apaga suas mensagens na DM definida')
    print('   !status                   - Mostra qual DM está definida')

@bot.command(name='definir_dm')
async def definir_dm(ctx, channel_id: int):
    """
    Uso: !definir_dm <ID_DO_CANAL_DM>
    Define o canal privado que será limpo.
    """
    global canal_alvo_id

    channel = bot.get_channel(channel_id)
    if channel is None:
        await ctx.send("❌ Canal não encontrado. Verifique o ID.")
        return

    if not isinstance(channel, discord.DMChannel):
        await ctx.send("❌ Isso não é um chat privado (DM). Use o ID de uma DM.")
        return

    canal_alvo_id = channel_id
    await ctx.send(f"✅ Canal definido: {channel.recipient} (ID: {channel_id})")

@bot.command(name='limpar')
async def limpar(ctx):
    """
    Uso: !limpar
    Apaga as últimas 1000 mensagens enviadas por VOCÊ na DM definida.
    """
    global canal_alvo_id

    if canal_alvo_id is None:
        await ctx.send("❌ Nenhuma DM definida. Use !definir_dm <ID> primeiro.")
        return

    channel = bot.get_channel(canal_alvo_id)
    if channel is None:
        await ctx.send("❌ Canal não encontrado. Defina novamente com !definir_dm.")
        canal_alvo_id = None
        return

    if not isinstance(channel, discord.DMChannel):
        await ctx.send("❌ O ID salvo não é uma DM. Defina novamente.")
        canal_alvo_id = None
        return

    await ctx.send(f"🔍 Iniciando limpeza em {channel.recipient}... (últimas 1000 mensagens)")

    count = 0
    limit = 1000  # ← ajuste se quiser mais

    async for message in channel.history(limit=limit):
        if message.author == bot.user:
            try:
                await message.delete()
                count += 1
                if count % 30 == 0:
                    await asyncio.sleep(0.5)
            except discord.HTTPException as e:
                print(f"⚠️ Erro ao deletar: {e}")

    await ctx.send(f"✅ Deletadas {count} mensagens suas em {channel.recipient}.")

@bot.command(name='status')
async def status(ctx):
    """
    Uso: !status
    Mostra qual DM está definida atualmente.
    """
    global canal_alvo_id

    if canal_alvo_id is None:
        await ctx.send("📌 Nenhuma DM definida. Use !definir_dm <ID>")
        return

    channel = bot.get_channel(canal_alvo_id)
    if channel is None:
        await ctx.send("❌ O ID salvo não é mais válido. Defina novamente.")
        canal_alvo_id = None
        return

    await ctx.send(f"📌 DM definida: {channel.recipient} (ID: {canal_alvo_id})")

# ============================================================
# 3. INICIALIZAÇÃO
# ============================================================

if __name__ == "__main__":
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Token inválido. Verifique se você copiou corretamente.")
    except KeyboardInterrupt:
        print("\n👋 Bot encerrado pelo usuário.")
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")