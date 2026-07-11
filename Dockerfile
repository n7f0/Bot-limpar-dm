FROM python:3.11-slim

# Instala dependências de sistema necessárias para o curl_cffi e psycopg2
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libcurl4-openssl-dev \
    libssl-dev \
    python3-dev \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "Discord.py"]
