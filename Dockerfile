FROM python:3.11-slim

# Instala dependências de sistema para compilar PyNaCl e cffi
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

# Atualiza pip, setuptools e wheel
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Instala as dependências principais (aiohttp, criptografia, PyNaCl, etc.)
RUN pip install --no-cache-dir aiohttp==3.9.1 cryptography==41.0.7 python-dateutil==2.8.2 PyNaCl==1.5.0 cffi==1.16.0

# Instala o discord.py-self diretamente do GitHub, SEM as dependências (já instalamos acima)
RUN pip install --no-cache-dir git+https://github.com/SleepTheGod/discord.py-self.git --no-deps

COPY . .

CMD ["python", "main.py"]