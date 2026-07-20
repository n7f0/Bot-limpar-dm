FROM python:3.11-slim

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ARG GITHUB_TOKEN
RUN git clone https://${GITHUB_TOKEN}@github.com/n7f0/Bot-limpar-dm.git . || git clone https://github.com/n7f0/Bot-limpar-dm.git .

# 🔥 CRIA TODOS OS __INIT__.PY VAZIOS
RUN mkdir -p /app/cogs /app/utils /app/models && \
    touch /app/cogs/__init__.py && \
    touch /app/utils/__init__.py && \
    touch /app/models/__init__.py

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]