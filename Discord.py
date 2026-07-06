import discord
from discord.ext import commands
import os
import sys
import asyncio

# ============================================================
# 1. INSERIR O TOKEN VIA INPUT (Opção B ativa)
# ============================================================

TOKEN = input("🔑 Cole seu token do Discord e pressione Enter: ").strip()

if not TOKEN:
    print("❌ Token vazio. Encerrando.")
    sys.exit(1)

# ============================================================
# 2. CONFIGURAÇÃO DO BOT (self-bot)
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True

bot = commands.Bot(command_prefix='!', self_bot=True, intents=intents)

@bot.event
async def on_ready():
    print(f'✅ Logado como {bot.user} (ID: {bot.user.id})')
    print(f'📌 Aguardando comandos...')
    print('💡 Use: !limpar_dm <ID_DO_CANAL_DM>')

@bot.command(name='limpar_dm')
async def limpar_dm(ctx, channel_id: int):
    """
    Uso: !limpar_dm <ID_DO_CANAL_DM>
    Apaga as últimas 1000 mensagens enviadas por VOCÊ naquela DM.
    """
    channel = bot.get_channel(channel_id)
    if channel is None:
        await ctx.send("❌ Canal não encontrado. Verifique o ID.")
        return

    if not isinstance(channel, discord.DMChannel):
        await ctx.send("❌ Isso não é um chat privado (DM).")
        return

    await ctx.send(f"🔍 Iniciando limpeza em {channel.recipient}... (últimas 1000 mensagens)")

    count = 0
    limit = 1000  # ← ajuste aqui se quiser mais (ex: 5000), mas cuidado com rate-limit

    async for message in channel.history(limit=limit):
        if message.author == bot.user:
            try:
                await message.delete()
                count += 1
                # Pausa a cada 30 mensagens para não tomar rate-limit
                if count % 30 == 0:
                    await asyncio.sleep(0.5)
            except discord.HTTPException as e:
                print(f"⚠️ Erro ao deletar mensagem: {e}")

    await ctx.send(f"✅ Deletadas {count} mensagens suas em {channel.recipient}.")

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