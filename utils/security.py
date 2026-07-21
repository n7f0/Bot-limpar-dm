import os
from cryptography.fernet import Fernet

ENCRYPTION_KEY = None

def load_encryption_key():
    global ENCRYPTION_KEY
    key = os.getenv('ENCRYPTION_KEY')
    if not key:
        key_file = '/app/data/secret.key'  # dentro de data
        os.makedirs(os.path.dirname(key_file), exist_ok=True)
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