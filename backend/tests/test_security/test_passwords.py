"""Password hashing tests — Argon2id round-trip and rejection cases."""

import pytest

from app.security.passwords import hash_password, verify_password

pytestmark = pytest.mark.unit


class TestHashPassword:
    def test_hash_is_not_plaintext(self):
        hashed = hash_password("correct horse battery staple")
        assert hashed != "correct horse battery staple"

    def test_hash_is_argon2_encoded(self):
        hashed = hash_password("correct horse battery staple")
        assert hashed.startswith("$argon2id$")

    def test_hashing_same_password_twice_yields_different_hashes(self):
        # Argon2 salts each hash randomly — this is what prevents rainbow-table attacks.
        first = hash_password("correct horse battery staple")
        second = hash_password("correct horse battery staple")
        assert first != second


class TestVerifyPassword:
    def test_correct_password_verifies(self):
        hashed = hash_password("correct horse battery staple")
        assert verify_password(hashed, "correct horse battery staple") is True

    def test_wrong_password_rejected(self):
        hashed = hash_password("correct horse battery staple")
        assert verify_password(hashed, "wrong password") is False

    def test_malformed_hash_rejected_not_raised(self):
        assert verify_password("not-a-real-hash", "anything") is False

    def test_empty_hash_rejected_not_raised(self):
        assert verify_password("", "anything") is False
