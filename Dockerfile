FROM python:3.11-slim

# Atualiza e instala dependências de sistema para compilar PyNaCl, cffi e discord.py-self
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

# Copia apenas o requirements primeiro para aproveitar cache do Docker
COPY requirements.txt .

# Instala as dependências Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia o restante do código
COPY . .

CMD ["python", "main.py"]