import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    raw = os.environ.get('FERNET_KEY', '').strip()
    if raw:
        return Fernet(raw.encode())
    # Dériver une clé depuis SECRET_KEY pour ne pas forcer une variable supplémentaire
    from config import Config
    derived = base64.urlsafe_b64encode(
        hashlib.sha256(Config.SECRET_KEY.encode()).digest()
    )
    return Fernet(derived)


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ''
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ''
    # Migration douce : valeurs legacy (non chiffrées) retournées telles quelles
    if not ciphertext.startswith('gAAAAA'):
        return ciphertext
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception):
        return ''
