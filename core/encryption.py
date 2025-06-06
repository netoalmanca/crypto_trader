# core/encryption.py
import base64
from django.conf import settings
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Helper para garantir que a chave tenha o tamanho certo para Fernet
def _get_key_from_settings():
    """
    Derives a valid Fernet key from the DJANGO_FIELD_ENCRYPTION_KEY in settings.
    This ensures the key is 32 bytes long and URL-safe base64 encoded.
    """
    config_key = settings.FIELD_ENCRYPTION_KEY
    if not config_key:
        raise ValueError("DJANGO_FIELD_ENCRYPTION_KEY is not set in your environment variables.")
        
    # Usar um KDF (Key Derivation Function) é uma boa prática para gerar a chave.
    # Usamos a própria chave como "senha" e um "salt" fixo (poderia vir do settings também).
    salt = b'some-fixed-salt-for-crypto' # Isso deve ser consistente
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000, # Número de iterações recomendado
    )
    key = base64.urlsafe_b64encode(kdf.derive(config_key.encode()))
    return key

def encrypt(data_str: str) -> str:
    """
    Encrypts a string and returns a URL-safe, base64-encoded string.
    """
    if not data_str:
        return ""
    try:
        key = _get_key_from_settings()
        f = Fernet(key)
        encrypted_data = f.encrypt(data_str.encode('utf-8'))
        return encrypted_data.decode('utf-8')
    except Exception as e:
        # Log the error in a real application
        print(f"Encryption failed: {e}")
        # Retornar uma string que indica falha ou levantar uma exceção
        raise ValueError("Failed to encrypt data.") from e

def decrypt(encrypted_token_str: str) -> str:
    """
    Decrypts a token string and returns the original string.
    """
    if not encrypted_token_str:
        return ""
    try:
        key = _get_key_from_settings()
        f = Fernet(key)
        decrypted_data = f.decrypt(encrypted_token_str.encode('utf-8'))
        return decrypted_data.decode('utf-8')
    except Exception as e:
        # Log the error in a real application
        print(f"Decryption failed. This can happen if the key changed or the data is corrupt. Error: {e}")
        # Pode ser útil retornar um valor específico para indicar falha na descriptografia
        return "DECRYPTION_FAILED"
