FROM python:3.11-slim

# Dependências de sistema para compilar PyNaCl e outras libs
RUN apt-get update && apt-get install -y \
    libsodium-dev \
    libsodium23 \
    build-essential \
    python3-dev \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia e instala as dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]