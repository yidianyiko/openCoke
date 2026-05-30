from __future__ import annotations

from argon2 import PasswordHasher as Argon2PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


class PasswordHasher:
    def __init__(self) -> None:
        self._hasher = Argon2PasswordHasher()

    def hash(self, password: str) -> str:
        _require_password(password)
        return self._hasher.hash(password)

    def verify(self, stored_hash: str, password: str) -> bool:
        _require_password(password)
        try:
            return self._hasher.verify(stored_hash, password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False


def _require_password(password: str) -> None:
    if not isinstance(password, str) or password == "":
        raise ValueError("password_required")
