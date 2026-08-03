"""
Password hashing — Argon2id via argon2-cffi.

Argon2id is the OWASP-recommended default for password storage (winner of the
Password Hashing Competition). We use the library's own tuned defaults rather
than hand-picking time/memory cost parameters — those defaults are chosen by
the argon2-cffi maintainers to balance security and server load, and are
periodically revised as hardware improves.
"""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    """Hash a plaintext password. Returns an encoded string safe to store —
    it embeds the algorithm, version, and cost parameters, so verification
    never needs the original parameters passed back in."""
    return _hasher.hash(plain)


def verify_password(hashed: str, plain: str) -> bool:
    """Check a plaintext password against a stored Argon2 hash.
    Returns False on mismatch or a malformed/foreign hash — never raises."""
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHash):
        return False
