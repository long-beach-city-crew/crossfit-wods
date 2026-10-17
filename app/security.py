"""Password hashing (stdlib scrypt) and the session signing key."""

import hashlib
import hmac
import os
import secrets

from app.db import INSTANCE_DIR

_SCRYPT = {"n": 2**14, "r": 8, "p": 1}


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    _, salt, digest = stored.split("$")
    candidate = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), **_SCRYPT)
    return hmac.compare_digest(candidate.hex(), digest)


# Checked against when the email is unknown, so a failed login takes the same time either way.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def secret_key() -> str:
    """SECRET_KEY from the environment, else one generated once and kept in instance/."""
    if key := os.environ.get("SECRET_KEY"):
        return key
    path = INSTANCE_DIR / "secret_key"
    if not path.exists():
        INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    return path.read_text(encoding="utf-8").strip()
