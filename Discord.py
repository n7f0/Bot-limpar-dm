import discord
from discord.ext import commands
import tkinter as tk
from tkinter import scrolledtext, messagebox
import threading
import asyncio

class DiscordSelfBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Self-Bot Discord - Limpar DM")
        self.root.geometry("600x500")
        self.root.resizable(False, False)

        # Token input
        tk.Label(root, text="Cole seu Token de Usuário:", font=("Arial", 12)).pack(pady=5)
        self.token_entry = tk.Entry(root, width=60, show="*")
        self.token_entry.pack(pady=5)

        # Botão de mostrar/ocultar token
        self.show_token = tk.BooleanVar(value=False)
        tk.Checkbutton(root, text="Mostrar Token", variable=self.show_token, command=self.toggle_token_visibility).pack()

        # Botão iniciar
        self.start_button = tk.Button(root, text="Iniciar Bot", command=self.start_bot, bg="green", fg="white", font=("Arial", 12))
        self.start_button.pack(pady=10)

        # Área de logs
        self.log_area = scrolledtext.ScrolledText(root, width=70, height=20, state='disabled')
        self.log_area.pack(pady=5)

        self.bot_thread = None
        self.bot_instance = None
        self.loop = asyncio.new_event_loop()

    def toggle_token_visibility(self):
        if self.show_token.get():
            self.token_entry.config(show="")
        else:
            self.token_entry.config(show="*")

    def log(self, msg):
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, msg + "\n")
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')
        self.root.update()

    def start_bot(self):
        token = self.token_entry.get().strip()
        if not token:
            messagebox.showerror("Erro", "Por favor, cole um token válido.")
            return

        self.start_button.config(state='disabled', text='Iniciando...')
        self.log("Iniciando bot com token...")

        # Iniciar o bot em uma thread separada para não travar a GUI
        self.bot_thread = threading.Thread(target=self.run_bot, args=(token,), daemon=True)
        self.bot_thread.start()

    def run_bot(self, token):
        # Cria o bot com self_bot=True
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True

        bot = commands.Bot(command_prefix='!', self_bot=True, intents=intents)

        @bot.event
        async def on_ready():
            self.log(f"✅ Bot logado como {bot.user} (ID: {bot.user.id})")
            self.start_button.config(state='normal', text='Bot Ativo', bg='blue')
            self.log("Comando disponível: !limpar_dm <ID_DO_CANAL>")

        @bot.command(name='limpar_dm')
        async def limpar_dm(ctx, channel_id: int):
            try:
                channel = bot.get_channel(channel_id)
                if channel is None or not isinstance(channel, discord.DMChannel):
                    await ctx.send("ID inválido ou não é uma DM.")
                    return

                await ctx.send(f"🔍 Apagando minhas mensagens em {channel.recipient}...")
                self.log(f"Apagando mensagens no canal {channel_id} (com {channel.recipient})")

                count = 0
                async for message in channel.history(limit=None):
                    if message.author == bot.user:
                        try:
                            await message.delete()
                            count += 1
                            # Pequena pausa para evitar rate limit (opcional)
                            await asyncio.sleep(0.2)
                        except discord.HTTPException as e:
                            self.log(f"Erro ao deletar mensagem: {e}")
                            break

                await ctx.send(f"✅ Deletadas {count} mensagens minhas no chat.")
                self.log(f"Deletadas {count} mensagens.")
            except Exception as e:
                self.log(f"❌ Erro no comando: {e}")
                await ctx.send(f"Erro: {e}")

        # Rodar o bot
        try:
            bot.run(token, bot=True)  # self_bot já setado
        except Exception as e:
            self.log(f"❌ Falha ao iniciar bot: {e}")
            self.start_button.config(state='normal', text='Iniciar Bot', bg='green')

# Iniciar a interface
if __name__ == "__main__":
    root = tk.Tk()
    app = DiscordSelfBotGUI(root)
    root.mainloop()