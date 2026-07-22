FROM python:3.11-slim

# Instala dependências de sistema (inclui git para clonar o discord.py-self)
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

# Copia o requirements primeiro
COPY requirements.txt .

# Instala todas as dependências em uma única linha com verbose para ver o erro
RUN pip install --no-cache-dir -r requirements.txt --verbose

COPY . .

CMD ["python", "main.py"]