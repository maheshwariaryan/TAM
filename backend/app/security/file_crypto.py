"""
At-rest envelope encryption for files — AES-256-GCM via the `cryptography` package.

GCM is an authenticated mode: `decrypt_bytes` raises `InvalidTag` if the
ciphertext (or the nonce) has been tampered with, so corruption/tampering is
detected rather than silently returning garbage plaintext. Never roll your
own crypto — this is a thin wrapper over a well-vetted primitive
(`cryptography.hazmat.primitives.ciphers.aead.AESGCM`), not a new algorithm.

Wire format: `nonce (12 bytes) || ciphertext+tag`. The nonce is generated
fresh per encryption call via `os.urandom` — reusing a nonce with the same
key breaks GCM's security guarantees entirely, so never persist/reuse one.
"""

import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_SIZE = 12
KEY_SIZE = 32  # AES-256


class FileCryptoError(Exception):
    pass


def encrypt_bytes(plaintext: bytes, key: bytes) -> bytes:
    """Encrypt plaintext with AES-256-GCM. `key` must be exactly 32 raw bytes."""
    if len(key) != KEY_SIZE:
        raise FileCryptoError(f"Encryption key must be {KEY_SIZE} bytes, got {len(key)}")
    nonce = os.urandom(NONCE_SIZE)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ciphertext


def decrypt_bytes(blob: bytes, key: bytes) -> bytes:
    """Decrypt a blob produced by encrypt_bytes. Raises FileCryptoError if the
    blob is truncated, the key is wrong, or the ciphertext/nonce was tampered
    with (GCM authentication tag mismatch)."""
    if len(key) != KEY_SIZE:
        raise FileCryptoError(f"Encryption key must be {KEY_SIZE} bytes, got {len(key)}")
    if len(blob) < NONCE_SIZE:
        raise FileCryptoError("Ciphertext too short to contain a nonce")
    nonce, ciphertext = blob[:NONCE_SIZE], blob[NONCE_SIZE:]
    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(nonce, ciphertext, None)
    except InvalidTag as exc:
        raise FileCryptoError(
            "Decryption failed — ciphertext or key is invalid (data tampered, "
            "corrupted, or wrong encryption key)"
        ) from exc
