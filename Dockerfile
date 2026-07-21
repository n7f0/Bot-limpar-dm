FROM python:3.11-slim

# Instala dependências de sistema para compilar PyNaCl e ffmpeg
RUN apt-get update && apt-get install -y \
    libsodium-dev \
    build-essential \
    python3-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]