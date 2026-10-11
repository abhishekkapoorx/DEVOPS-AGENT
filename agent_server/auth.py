"""Short-lived signed access tokens for the server transport."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class AccessClaims:
    user_id: str
    expires_at: int


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def issue_access_token(secret: str, user_id: str, ttl_seconds: int = 900) -> str:
    if not secret or not user_id or ttl_seconds < 1:
        raise ValueError("secret, user_id, and a positive TTL are required")
    payload = _encode(json.dumps({"sub": user_id, "exp": int(time.time()) + ttl_seconds}, separators=(",", ":")).encode())
    signature = _encode(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
    return f"da1.{payload}.{signature}"


def verify_access_token(token: str, secret: str) -> AccessClaims | None:
    try:
        prefix, payload, signature = token.split(".", 2)
        if prefix != "da1":
            return None
        expected = _encode(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        data = json.loads(_decode(payload))
        if not isinstance(data.get("sub"), str) or int(data["exp"]) <= int(time.time()):
            return None
        return AccessClaims(user_id=data["sub"], expires_at=int(data["exp"]))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        return None


__all__ = ["AccessClaims", "issue_access_token", "verify_access_token"]
