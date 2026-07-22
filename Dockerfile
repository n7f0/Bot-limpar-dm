FROM python:3.11-slim

# Instala dependências de sistema para compilar PyNaCl, cffi e discord.py-self
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

# Copia requirements e instala com --no-cache-dir e --force-reinstall
COPY requirements.txt .
RUN pip install --no-cache-dir --force-reinstall -r requirements.txt

# Verifica se o discord.py-self foi instalado corretamente
RUN python -c "import discord; print(f'✅ discord version: {discord.__version__}')"

COPY . .

CMD ["python", "main.py"]