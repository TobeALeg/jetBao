from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass


PBKDF2_ITERATIONS = 120_000
TOKEN_TTL_SECONDS = 60 * 60 * 12


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_value, digest_value = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_value.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_value.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


@dataclass(frozen=True)
class TokenPayload:
    user_id: int
    expires_at: int


def create_token(user_id: int, secret_key: str) -> str:
    expires_at = int(time.time()) + TOKEN_TTL_SECONDS
    nonce = secrets.token_urlsafe(12)
    body = f"{user_id}.{expires_at}.{nonce}"
    signature = hmac.new(secret_key.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{body}.{encoded_signature}"


def parse_token(token: str, secret_key: str) -> TokenPayload | None:
    try:
        user_id_value, expires_value, nonce, signature = token.split(".", 3)
        body = f"{user_id_value}.{expires_value}.{nonce}"
        expected = hmac.new(secret_key.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
        expected_value = base64.urlsafe_b64encode(expected).decode("ascii").rstrip("=")
        if not hmac.compare_digest(signature, expected_value):
            return None
        expires_at = int(expires_value)
        if expires_at < int(time.time()):
            return None
        return TokenPayload(user_id=int(user_id_value), expires_at=expires_at)
    except (ValueError, TypeError):
        return None

