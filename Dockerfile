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

# Instala as dependências em duas etapas para evitar conflitos
RUN pip install --no-cache-dir aiohttp cryptography python-dateutil PyNaCl cffi
RUN pip install --no-cache-dir discord.py-self==2.3.2

COPY . .

CMD ["python", "main.py"]