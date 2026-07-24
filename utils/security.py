import os
from cryptography.fernet import Fernet
import logging

logger = logging.getLogger(__name__)
ENCRYPTION_KEY = None

def load_encryption_key():
    global ENCRYPTION_KEY
    # Pega a chave e limpa qualquer espaço invisível ou quebra de linha
    raw_key = os.getenv('ENCRYPTION_KEY', '').strip()
    
    # Remove aspas se você tiver colocado sem querer no .env
    raw_key = raw_key.replace('"', '').replace("'", "")
    
    try:
        # Testa se a chave limpa é válida para a matemática do Fernet
        Fernet(raw_key.encode())
        ENCRYPTION_KEY = raw_key.encode()
        logger.info("✅ Chave de criptografia carregada com sucesso do .env")
    except Exception as e:
        logger.warning("⚠️ Chave ENCRYPTION_KEY no .env está inválida ou vazia.")
        logger.warning("🔄 Gerando uma chave provisória na memória para o bot não travar...")
        # Gera uma chave 100% válida dinamicamente se tudo der errado
        ENCRYPTION_KEY = Fernet.generate_key()

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
