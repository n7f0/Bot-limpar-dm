FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libsodium-dev \
    libsodium23 \
    build-essential \
    python3-dev \
    libffi-dev \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Atualiza pip
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Instala dependências básicas primeiro (sem discord.py-self)
COPY requirements.txt .
RUN pip install --no-cache-dir aiohttp cryptography python-dateutil PyNaCl cffi

# Instala o discord.py-self separadamente (com verbose)
RUN pip install --no-cache-dir git+https://github.com/SleepTheGod/discord.py-self.git --verbose

COPY . .

CMD ["python", "main.py"]