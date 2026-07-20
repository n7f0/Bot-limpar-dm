FROM python:3.11-slim

# Instala git e dependências
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone do repositório (opcional, mas mantido)
ARG GITHUB_TOKEN
RUN git clone https://${GITHUB_TOKEN}@github.com/n7f0/Bot-limpar-dm.git . || git clone https://github.com/n7f0/Bot-limpar-dm.git .

# Cria estrutura de pastas
RUN mkdir -p /app/cogs /app/utils /app/models /app/data

# 🔥 CRIA TODOS OS __init__.py VAZIOS (fundamental)
RUN touch /app/cogs/__init__.py /app/utils/__init__.py /app/models/__init__.py

# 🔥 CRIA O PANEL.PY (garantido)
RUN cat > /app/cogs/panel.py <<'EOF'
import discord
from discord import app_commands
from discord.ext import commands
from models.user import User
from utils.logger import get_logger

logger = get_logger(__name__)

class Panel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='painel', description='Abre o painel de controle')
    async def painel(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user = User(interaction.user.id)
        embed = discord.Embed(title='🛡️ Dashboard', color=discord.Color.blue())
        tokens = user.data.get('tokens', [])
        embed.add_field(name='Tokens', value=f'{len(tokens)} configurados', inline=True)
        embed.add_field(
            name='Canal de Limpeza',
            value=f'<#{user.data.get("chat_id")}>' if user.data.get('chat_id') else 'Não definido',
            inline=False
        )
        embed.add_field(
            name='Auto-Farm',
            value='✅ Ativo' if user.data.get('auto_farming') else '❌ Inativo',
            inline=True
        )
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Panel(bot))
EOF

# 🔥 CRIA O MAIN.PY
RUN cat > /app/main.py <<'EOF'
import discord
from discord.ext import commands
import os
import asyncio
from utils.logger import get_logger
from utils.db import init_db
from utils.security import load_encryption_key

logger = get_logger()
load_encryption_key()

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix='!', intents=intents)

async def load_extensions():
    cogs = [
        "cogs.panel",
        "cogs.voice",
        "cogs.clean",
        "cogs.backup",
        "cogs.farm",
        "cogs.profile",
        "cogs.admin"
    ]
    for cog in cogs:
        try:
            await bot.load_extension(cog)
            logger.info(f"✅ Cog carregado: {cog}")
        except Exception as e:
            logger.error(f"❌ Erro ao carregar {cog}: {e}")

@bot.event
async def on_ready():
    logger.info(f"✅ Bot logado como {bot.user}")
    try:
        synced = await bot.tree.sync()
        logger.info(f"✅ {len(synced)} comandos sincronizados.")
    except Exception as e:
        logger.error(f"❌ Erro ao sincronizar: {e}")
    bot.loop.create_task(update_presence())

async def update_presence():
    while True:
        try:
            if bot.is_ready():
                activity = discord.Activity(
                    type=discord.ActivityType.playing,
                    name="Nexzy Pro",
                    details=f"🧹 {len(bot.users)} usuários",
                    state="Modo Stealth"
                )
                await bot.change_presence(activity=activity, status=discord.Status.online)
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Erro na presença: {e}")
            await asyncio.sleep(10)

if __name__ == "__main__":
    async def main():
        async with bot:
            init_db()
            await load_extensions()
            token = os.getenv('BOT_TOKEN')
            if not token:
                logger.error("❌ BOT_TOKEN não definido.")
                return
            await bot.start(token)
    asyncio.run(main())
EOF

# 🔥 CRIA UTILS/LOGGER.PY
RUN cat > /app/utils/logger.py <<'EOF'
import logging
import sys

def get_logger(name=None):
    logger = logging.getLogger(name or 'bot')
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)-8s %(name)s %(message)s'))
        logger.addHandler(handler)
    return logger
EOF

# 🔥 CRIA UTILS/DB.PY
RUN cat > /app/utils/db.py <<'EOF'
import sqlite3
import os
import json

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'config.db')

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            tokens TEXT,
            default_token_index INTEGER DEFAULT 0,
            chat_id INTEGER,
            farm_chat_id INTEGER,
            auto_farming INTEGER DEFAULT 0,
            farm_interval INTEGER DEFAULT 120,
            farm_message TEXT,
            sleep_mode INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
EOF

# 🔥 CRIA UTILS/SECURITY.PY
RUN cat > /app/utils/security.py <<'EOF'
import os
from cryptography.fernet import Fernet

ENCRYPTION_KEY = None

def load_encryption_key():
    global ENCRYPTION_KEY
    key = os.getenv('ENCRYPTION_KEY')
    if not key:
        key_file = '/app/secret.key'
        if os.path.exists(key_file):
            with open(key_file, 'r') as f:
                key = f.read().strip()
        else:
            key = Fernet.generate_key().decode()
            with open(key_file, 'w') as f:
                f.write(key)
    ENCRYPTION_KEY = key.encode()

def encrypt(text: str) -> str:
    if not text:
        return ''
    f = Fernet(ENCRYPTION_KEY)
    return f.encrypt(text.encode()).decode()

def decrypt(token: str) -> str:
    if not token:
        return ''
    f = Fernet(ENCRYPTION_KEY)
    return f.decrypt(token.encode()).decode()
EOF

# 🔥 CRIA MODELS/USER.PY
RUN cat > /app/models/user.py <<'EOF'
import json
from utils.db import get_connection

class User:
    def __init__(self, user_id):
        self.user_id = user_id
        self.data = self._load()
    
    def _load(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (self.user_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            data = dict(row)
            if data.get('tokens'):
                data['tokens'] = json.loads(data['tokens'])
            else:
                data['tokens'] = []
            return data
        return {'tokens': [], 'default_token_index': 0}
    
    def save(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users (
                user_id, tokens, default_token_index, chat_id, farm_chat_id,
                auto_farming, farm_interval, farm_message, sleep_mode, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (
            self.user_id,
            json.dumps(self.data.get('tokens', [])),
            self.data.get('default_token_index', 0),
            self.data.get('chat_id'),
            self.data.get('farm_chat_id'),
            self.data.get('auto_farming', 0),
            self.data.get('farm_interval', 120),
            self.data.get('farm_message', ''),
            self.data.get('sleep_mode', 0)
        ))
        conn.commit()
        conn.close()
    
    def get_token(self, index=None):
        if index is None:
            index = self.data.get('default_token_index', 0)
        tokens = self.data.get('tokens', [])
        if tokens and index < len(tokens):
            return tokens[index]
        return None
EOF

# 🔥 CRIA REQUIREMENTS.TXT (se não existir)
RUN cat > /app/requirements.txt <<'EOF'
discord.py>=2.3.0
aiohttp>=3.8.0
curl_cffi>=0.5.0
dnspython>=2.4.0
psycopg2-binary>=2.9.0
cryptography>=39.0.0
python-dateutil>=2.8.2
EOF

# Instala dependências
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]