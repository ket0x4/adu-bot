import os
import hmac
import hashlib
import base64
import secrets
from pathlib import Path

KEY_FILE = os.getenv("ENCRYPTION_KEY_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".secret.key"))

def _get_master_key() -> bytes:
    """Retrieves or generates the persistent master encryption key."""
    env_key = os.getenv("ENCRYPTION_KEY", "").strip()
    if env_key:
        return hashlib.sha256(env_key.encode('utf-8')).digest()

    if os.path.exists(KEY_FILE):
        try:
            with open(KEY_FILE, "rb") as f:
                key_data = f.read().strip()
                if len(key_data) >= 32:
                    return key_data[:32]
        except Exception:
            pass

    # Generate new random key and persist it with strict file permissions
    new_key = secrets.token_bytes(32)
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        mode = 0o600
        fd = os.open(KEY_FILE, flags, mode)
        with os.fdopen(fd, "wb") as f:
            f.write(new_key)
    except Exception:
        pass
    return new_key

_MASTER_KEY = _get_master_key()

def _derive_keys(master_key: bytes, salt: bytes):
    """Derives encryption key and MAC key using PBKDF2-HMAC-SHA256."""
    derived = hashlib.pbkdf2_hmac('sha256', master_key, salt, 100000, dklen=64)
    return derived[:32], derived[32:]

def encrypt_text(plain_text: str) -> str:
    """Encrypts plaintext using authenticated keystream cipher (PBKDF2 + CTR + HMAC-SHA256).
    Returns token prefixed with enc:v1:
    """
    if not plain_text:
        return ""
    if plain_text.startswith("enc:v1:"):
        return plain_text

    plain_bytes = plain_text.encode('utf-8')
    salt = secrets.token_bytes(16)
    iv = secrets.token_bytes(16)
    enc_key, mac_key = _derive_keys(_MASTER_KEY, salt)

    # CTR keystream generator via SHA-256 blocks
    keystream = bytearray()
    counter = 0
    while len(keystream) < len(plain_bytes):
        block = hashlib.sha256(enc_key + iv + counter.to_bytes(4, 'big')).digest()
        keystream.extend(block)
        counter += 1

    cipher = bytes(p ^ k for p, k in zip(plain_bytes, keystream[:len(plain_bytes)]))
    tag = hmac.new(mac_key, salt + iv + cipher, hashlib.sha256).digest()
    payload = salt + iv + tag + cipher
    return "enc:v1:" + base64.urlsafe_b64encode(payload).decode('ascii')

def decrypt_text(cipher_text: str) -> str:
    """Decrypts token prefixed with enc:v1:. If not encrypted, returns as-is for backwards compatibility."""
    if not cipher_text:
        return ""
    if not cipher_text.startswith("enc:v1:"):
        return cipher_text

    try:
        raw = base64.urlsafe_b64decode(cipher_text[7:])
        if len(raw) < 48:
            return cipher_text
        salt = raw[:16]
        iv = raw[16:32]
        tag = raw[32:64]
        cipher = raw[64:]

        enc_key, mac_key = _derive_keys(_MASTER_KEY, salt)
        expected_tag = hmac.new(mac_key, salt + iv + cipher, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected_tag):
            raise ValueError("Integrity check failed: corrupted or tampered ciphertext")

        keystream = bytearray()
        counter = 0
        while len(keystream) < len(cipher):
            block = hashlib.sha256(enc_key + iv + counter.to_bytes(4, 'big')).digest()
            keystream.extend(block)
            counter += 1

        plain_bytes = bytes(c ^ k for c, k in zip(cipher, keystream[:len(cipher)]))
        return plain_bytes.decode('utf-8')
    except Exception:
        # In case of any decryption failure, return original or error
        return cipher_text
