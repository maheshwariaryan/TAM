"""At-rest encryption tests — AES-256-GCM round-trip and tamper detection."""

import os

import pytest

from app.security.file_crypto import (
    KEY_SIZE,
    NONCE_SIZE,
    FileCryptoError,
    decrypt_bytes,
    encrypt_bytes,
)

pytestmark = pytest.mark.unit


def _key() -> bytes:
    return os.urandom(KEY_SIZE)


class TestEncryptDecryptRoundTrip:
    def test_round_trip_returns_original_plaintext(self):
        key = _key()
        plaintext = b"sensitive financial document contents"
        blob = encrypt_bytes(plaintext, key)
        assert decrypt_bytes(blob, key) == plaintext

    def test_ciphertext_does_not_contain_plaintext(self):
        key = _key()
        plaintext = b"sensitive financial document contents"
        blob = encrypt_bytes(plaintext, key)
        assert plaintext not in blob

    def test_nonce_is_prepended_and_random_per_call(self):
        key = _key()
        plaintext = b"same input, different nonce each time"
        blob1 = encrypt_bytes(plaintext, key)
        blob2 = encrypt_bytes(plaintext, key)
        assert blob1[:NONCE_SIZE] != blob2[:NONCE_SIZE]
        assert blob1 != blob2

    def test_empty_plaintext_round_trips(self):
        key = _key()
        blob = encrypt_bytes(b"", key)
        assert decrypt_bytes(blob, key) == b""


class TestTamperDetection:
    def test_flipped_ciphertext_byte_raises(self):
        key = _key()
        blob = bytearray(encrypt_bytes(b"do not tamper with me", key))
        blob[-1] ^= 0xFF  # flip a byte in the auth tag / ciphertext tail
        with pytest.raises(FileCryptoError):
            decrypt_bytes(bytes(blob), key)

    def test_flipped_nonce_byte_raises(self):
        key = _key()
        blob = bytearray(encrypt_bytes(b"do not tamper with me", key))
        blob[0] ^= 0xFF  # flip a byte inside the nonce
        with pytest.raises(FileCryptoError):
            decrypt_bytes(bytes(blob), key)

    def test_wrong_key_raises(self):
        blob = encrypt_bytes(b"encrypted with one key", _key())
        with pytest.raises(FileCryptoError):
            decrypt_bytes(blob, _key())

    def test_truncated_blob_raises(self):
        with pytest.raises(FileCryptoError):
            decrypt_bytes(b"short", _key())


class TestKeyValidation:
    def test_encrypt_rejects_wrong_key_length(self):
        with pytest.raises(FileCryptoError):
            encrypt_bytes(b"data", b"too-short-key")

    def test_decrypt_rejects_wrong_key_length(self):
        blob = encrypt_bytes(b"data", _key())
        with pytest.raises(FileCryptoError):
            decrypt_bytes(blob, b"too-short-key")
