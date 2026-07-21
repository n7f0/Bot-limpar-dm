FROM python:3.11-slim

# Aqui nós adicionamos o ffmpeg e o libopus0 junto com o git original
RUN apt-get update && apt-get install -y git ffmpeg libopus0 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ARG GITHUB_TOKEN
RUN git clone https://${GITHUB_TOKEN}@github.com/n7f0/Bot-limpar-dm.git . || git clone https://github.com/n7f0/Bot-limpar-dm.git .

RUN mkdir -p /app/cogs /app/utils /app/models && \
    echo "" > /app/cogs/__init__.py && \
    echo "" > /app/utils/__init__.py && \
    echo "" > /app/models/__init__.py

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
