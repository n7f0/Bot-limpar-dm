import os
from cryptography.fernet import Fernet
import logging

logger = logging.getLogger(__name__)
ENCRYPTION_KEY = None

def load_encryption_key():
    global ENCRYPTION_KEY
    key = os.getenv('ENCRYPTION_KEY')
    if not key:
        logger.error("CRÍTICO: Variável ENCRYPTION_KEY não definida no ambiente. Abortando.")
        exit(1)
    ENCRYPTION_KEY = key.encode()

def encrypt(text: str) -> str:
    if not text: return ''
    f = Fernet(ENCRYPTION_KEY)
    return f.encrypt(text.encode()).decode()

def decrypt(token: str) -> str:
    if not token: return ''
    try:
        f = Fernet(ENCRYPTION_KEY)
        return f.decrypt(token.encode()).decode()
    except Exception as e:
        logger.error(f"Erro ao descriptografar token: {e}")
        return ''
