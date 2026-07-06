import discord
from discord.ext import commands
import asyncio
import threading
import sys
from flask import Flask, request, render_template_string

# ============================================================
# FLASK - Servidor web para inserir token
# ============================================================
app = Flask(__name__)

# Variável global para armazenar o token e o bot
bot_instance = None
token_received = False

# Página HTML simples com formulário
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>Token do Bot</title>
    <style>
        body { font-family: Arial; max-width: 500px; margin: 50px auto; text-align: center; }
        input, button { padding: 10px; margin: 10px; width: 80%; }
        button { background: #5865F2; color: white; border: none; cursor: pointer; }
        button:hover { background: #4752C4; }
        .status { color: green; }
        .error { color: red; }
    </style>
</head>
<body>
    <h1>🤖 Discord Self-Bot</h1>
    <p>Cole seu token abaixo para iniciar o bot:</p>
    <form method="POST">
        <input type="text" name="token" placeholder="Cole seu token aqui..." required>
        <br>
        <button type="submit">Iniciar Bot</button>
    </form>
    {% if message %}
        <p class="{{ 'status' if success else 'error' }}">{{ message }}</p>
    {% endif %}
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    global token_received, bot_instance
    message = None
    success = False

    if request.method == 'POST':
        token = request.form.get('token', '').strip()
        if not token:
            message = "❌ Token vazio!"
            success = False
        else:
            # Se já tiver um bot rodando, encerra antes de iniciar outro
            if bot_instance and bot_instance.is_ready():
                # Não podemos parar o bot facilmente, mas podemos ignorar e avisar
                message = "⚠️ Bot já está rodando. Reinicie o serviço para trocar o token."
                success = False
            else:
                # Inicia o bot em uma thread separada
                try:
                    start_bot_thread(token)
                    message = "✅ Bot iniciado com sucesso! Volte para o Discord e use !limpar_dm."
                    success = True
                    token_received = True
                except Exception as e:
                    message = f"❌ Erro ao iniciar: {e}"
                    success = False

    return render_template_string(HTML_PAGE, message=message, success=success)

# ============================================================
# DISCORD BOT (self-bot)
# ============================================================
def run_bot(token):
    """Função que inicializa e roda o bot Discord."""
    intents = discord.Intents.default()
    intents.message_content = True
    intents.messages = True

    bot = commands.Bot(command_prefix='!', self_bot=True, intents=intents)

    @bot.event
    async def on_ready():
        print(f'✅ Logado como {bot.user} (ID: {bot.user.id})')
        print('📌 Aguardando comandos...')

    @bot.command(name='limpar_dm')
    async def limpar_dm(ctx, channel_id: int):
        """
        Uso: !limpar_dm <ID_DO_CANAL_DM>
        Apaga as últimas 1000 mensagens enviadas por VOCÊ na DM.
        """
        channel = bot.get_channel(channel_id)
        if channel is None:
            await ctx.send("❌ Canal não encontrado. Verifique o ID.")
            return

        if not isinstance(channel, discord.DMChannel):
            await ctx.send("❌ Isso não é um chat privado (DM).")
            return

        await ctx.send(f"🔍 Iniciando limpeza em {channel.recipient}... (últimas 1000)")

        count = 0
        limit = 1000
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

    try:
        bot.run(token)
    except discord.LoginFailure:
        print("❌ Token inválido.")
    except Exception as e:
        print(f"❌ Erro no bot: {e}")

def start_bot_thread(token):
    """Inicia o bot em uma thread separada para não bloquear o Flask."""
    thread = threading.Thread(target=run_bot, args=(token,), daemon=True)
    thread.start()
    global bot_instance
    # Armazenamos uma referência (opcional)
    # Não podemos acessar o bot diretamente de outra thread com segurança, mas é ok.
    bot_instance = thread

# ============================================================
# INICIALIZAÇÃO PRINCIPAL
# ============================================================
if __name__ == "__main__":
    # Inicia o servidor Flask na porta definida pelo Railway (ou 8080)
    port = int(os.environ.get("PORT", 8080))
    print(f"🌐 Servidor web rodando em http://0.0.0.0:{port}")
    print("🔑 Acesse no navegador para colocar o token.")
    app.run(host='0.0.0.0', port=port)