FROM python:3.11-slim

# Instala git e dependências do sistema
RUN apt-get update && apt-get install -y git gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone o repositório privado (token passado como build-arg)
ARG GITHUB_TOKEN
RUN git clone https://${GITHUB_TOKEN}@github.com/n7f0/Bot-limpar-dm.git .

# Instala dependências Python
RUN pip install --no-cache-dir -r requirements.txt

# Gera chave de criptografia (se não existir)
RUN python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" > /app/secret.key || true

CMD ["python", "main.py"]