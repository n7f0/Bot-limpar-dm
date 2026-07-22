FROM python:3.11-slim

# Instala dependências de sistema
RUN apt-get update && apt-get install -y \
    libsodium-dev \
    libsodium23 \
    build-essential \
    python3-dev \
    libffi-dev \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Atualiza pip, setuptools e wheel
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

WORKDIR /app

COPY requirements.txt .

# Instala as dependências base primeiro (com cffi e PyNaCl)
RUN pip install --no-cache-dir cffi>=1.15.0
RUN pip install --no-cache-dir PyNaCl>=1.5.0
RUN pip install --no-cache-dir aiohttp cryptography python-dateutil

# Instala o discord.py-self do GitHub sem dependências
RUN pip install --no-cache-dir --no-deps git+https://github.com/SleepTheGod/discord.py-self.git

# Instala as dependências restantes do discord.py-self (se houver)
RUN pip install --no-cache-dir discord.py-self[docs] 2>/dev/null || true

COPY . .

CMD ["python", "main.py"]