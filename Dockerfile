FROM python:3.11-slim

# Instala git e outras dependências
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# O token será passado como build-arg para acessar o repositório privado
ARG GITHUB_TOKEN
RUN git clone https://${GITHUB_TOKEN}@github.com/n7f0/Bot-limpar-dm.git .

# Instala dependências
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "Discord.py"]