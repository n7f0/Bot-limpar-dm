FROM python:3.11-slim

# Atualiza e instala dependências de sistema ESSENCIAIS
RUN apt-get update && apt-get install -y \
    libsodium-dev \
    libsodium23 \
    build-essential \
    python3-dev \
    libffi-dev \
    ffmpeg \
    git \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# Instala primeiro as dependências que não precisam compilação
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Instala as dependências com compilação separadamente para melhor controle
RUN pip install --no-cache-dir \
    cffi \
    PyNaCl==1.5.0 \
    aiohttp \
    cryptography \
    python-dateutil

# Instala o discord.py-self (que pode puxar outras dependências)
RUN pip install --no-cache-dir discord.py-self>=2.3.0

# Instala o restante do requirements.txt (caso haja algo mais)
RUN pip install --no-cache-dir -r requirements.txt || true

COPY . .

CMD ["python", "main.py"]