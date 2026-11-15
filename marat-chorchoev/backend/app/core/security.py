import hashlib
import json
import secrets
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error, InvalidHashError

_hasher = PasswordHasher()
# Verified against when the account does not exist, so timing does not reveal it.
_DUMMY_HASH = _hasher.hash("fixflow-dummy-password")


def hash_password(password: str) -> str:
    """Argon2id with the library's recommended parameters."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (Argon2Error, InvalidHashError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def payload_hash(payload: Any) -> str:
    """Stable digest of a command payload, used to detect idempotency-key reuse."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
