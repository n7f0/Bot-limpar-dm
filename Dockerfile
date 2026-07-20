FROM python:3.11-slim

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ARG GITHUB_TOKEN
RUN git clone https://${GITHUB_TOKEN}@github.com/n7f0/Bot-limpar-dm.git .

# (Opcional) Verifica se o arquivo panel.py existe
RUN ls -la /app/cogs/

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]