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

# Instala o discord.py-self e outras dependências direto
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir git+https://github.com/SleepTheGod/discord.py-self.git && \
    pip install --no-cache-dir aiohttp cryptography python-dateutil PyNaCl cffi

COPY . .

CMD ["python", "main.py"]