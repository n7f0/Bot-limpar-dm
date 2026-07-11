FROM python:3.10-slim

WORKDIR /app

# Instala dependências do sistema (para cloudscraper e outras)
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY Discord.py .

CMD ["python", "Discord.py"]