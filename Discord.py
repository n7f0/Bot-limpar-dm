import discord
from discord.ext import commands
import os

TOKEN = os.getenv('SEU_TOKEN_DE_USUARIO')  # NUNCA compartilhe!

bot = commands.Bot(command_prefix='!', self_bot=True)  # ativa modo self-bot

@bot.event
async def on_ready():
    print(f'Logado como {bot.user}')

@bot.command(name='limpar_dm')
async def limpar_dm(ctx, channel_id: int):
    channel = bot.get_channel(channel_id)
    if channel is None or not isinstance(channel, discord.DMChannel):
        await ctx.send("ID inválido ou não é uma DM.")
        return

    await ctx.send(f"Apagando minhas mensagens em {channel.recipient}...")

    count = 0
    async for message in channel.history(limit=None):
        if message.author == bot.user:   # você é o autor
            try:
                await message.delete()
                count += 1
            except discord.HTTPException:
                pass

    await ctx.send(f"Deletadas {count} mensagens.")

bot.run(TOKEN)
