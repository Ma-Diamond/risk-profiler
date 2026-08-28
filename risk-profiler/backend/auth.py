"""Authentication — password hashing and bearer tokens.

Deliberately simple and stateless (a signed JWT, not a server-side
session store) to match the rest of this backend's style. Two things
worth flagging honestly rather than glossing over, before this goes
anywhere near real production traffic:

- The frontend stores the token in localStorage, which is readable by
  any script on the page (XSS-exposed) — an httpOnly cookie with a
  short-lived access token + refresh token would be the harder-to-attack
  version.
- AUTH_SECRET_KEY below falls back to a random per-process secret if
  the env var isn't set, purely so local dev doesn't crash. That means
  every existing token is invalidated on every restart, which is a
  correctness footgun in anything beyond a laptop dev session, not just
  a security one. Set AUTH_SECRET_KEY explicitly for anything that
  needs tokens to survive a restart.
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
        # Malformed hash (shouldn't happen from our own hash_password, but
        # fail closed rather than raising a 500 on a bad stored value).
        return False


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + TOKEN_EXPIRY,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, _SECRET_KEY, algorithm=TOKEN_ALGORITHM)


def decode_token(token: str) -> int | None:
    """Returns the user_id if the token is valid and unexpired, else None.
    Never raises — callers treat None as "not authenticated" uniformly,
    whether that's because no token was given or because it's invalid."""
    try:
        payload = jwt.decode(token, _SECRET_KEY, algorithms=[TOKEN_ALGORITHM])
        return int(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        return None
