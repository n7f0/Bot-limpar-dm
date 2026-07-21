import os
import shutil
from cryptography.fernet import Fernet

ENCRYPTION_KEY = None

def load_encryption_key():
    global ENCRYPTION_KEY
    key = os.getenv('ENCRYPTION_KEY')
    if not key:
        key_file = '/app/secret.key'
        # Se for um diretório, remove e cria arquivo
        if os.path.isdir(key_file):
            shutil.rmtree(key_file)
        if not os.path.exists(key_file):
            key = Fernet.generate_key().decode()
            with open(key_file, 'w') as f:
                f.write(key)
        else:
            with open(key_file, 'r') as f:
                key = f.read().strip()
    ENCRYPTION_KEY = key.encode()

def encrypt(text: str) -> str:
    if not text:
        return ''
    f = Fernet(ENCRYPTION_KEY)
    return f.encrypt(text.encode()).decode()

def decrypt(token: str) -> str:
    if not token:
        return ''
    f = Fernet(ENCRYPTION_KEY)
    return f.decrypt(token.encode()).decode()