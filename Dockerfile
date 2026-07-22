FROM python:3.11-slim

# Instala dependências de sistema (essenciais para compilar PyNaCl e outras)
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

# Copia o requirements
COPY requirements.txt .

# Instala as dependências em partes para identificar falhas
RUN pip install --no-cache-dir aiohttp cryptography python-dateutil PyNaCl cffi setuptools wheel

# Tenta instalar o discord.py-self do PyPI (versão mais estável)
RUN pip install --no-cache-dir discord.py-self==2.3.2 || \
    pip install --no-cache-dir discord.py-self==2.3.0 || \
    pip install --no-cache-dir discord.py-self==2.2.0

COPY . .

CMD ["python", "main.py"]