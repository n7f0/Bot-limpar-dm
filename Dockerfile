FROM python:3.11-slim

# Instala git e outras dependências
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone o repositório (substitua pela URL do seu repositório)
# Use seu token de acesso pessoal se for privado, ou use HTTPS com credenciais
ARG GITHUB_TOKEN
RUN git clone https://${GITHUB_TOKEN}@github.com/seu-usuario/seu-repositorio.git . || git clone https://github.com/seu-usuario/seu-repositorio.git .

# Copia requirements.txt (se já estiver no repositório, o clone já trouxe)
# Mas se quiser garantir, copie localmente ou instale direto
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "Discord.py"]