import os
from cryptography.fernet import Fernet

ENCRYPTION_KEY = None

def load_encryption_key():
    global ENCRYPTION_KEY
    key = os.getenv('ENCRYPTION_KEY')
    if not key:
        key_file = '/app/secret.key'
        if os.path.exists(key_file):
            with open(key_file, 'r') as f:
                key = f.read().strip()
        else:
            key = Fernet.generate_key().decode()
            with open(key_file, 'w') as f:
                f.write(key)
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