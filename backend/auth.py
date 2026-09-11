"""Authentication — password hashing and bearer tokens.

Token subject is now the user's email (DynamoDB's Users table is keyed
by email, there's no separate numeric user id anymore) — decode_token
returns a plain string, not an int.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

TOKEN_ALGORITHM = "HS256"
TOKEN_EXPIRY = timedelta(days=14)

_SECRET_KEY = os.environ.get("AUTH_SECRET_KEY")
if not _SECRET_KEY:
    _SECRET_KEY = secrets.token_hex(32)
    print(
        "WARNING: AUTH_SECRET_KEY is not set — using a random per-process "
        "secret. Existing tokens will stop working on every restart. Set "
        "AUTH_SECRET_KEY in the environment for anything beyond local dev."
    )


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_token(email: str) -> str:
    payload = {
        "sub": email,
        "exp": datetime.now(timezone.utc) + TOKEN_EXPIRY,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, _SECRET_KEY, algorithm=TOKEN_ALGORITHM)


def decode_token(token: str) -> str | None:
    """Returns the email if the token is valid and unexpired, else None."""
    try:
        payload = jwt.decode(token, _SECRET_KEY, algorithms=[TOKEN_ALGORITHM])
        return str(payload["sub"])
    except (jwt.InvalidTokenError, KeyError):
        return None
