"""Redact credentials before evidence storage, model calls, and Slack posts."""

from __future__ import annotations

import json
import re
from typing import Any


_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")
_AWS = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
_CONNECTION_SECRET = re.compile(r"(?i)(://[^:/?#]+:)[^@]+(@)")
_LONG_TOKEN = re.compile(r"\b[A-Za-z0-9+/=_-]{40,}\b")
_SECRET_KEY = re.compile(r"(?i)(password|passwd|token|secret|api[_-]?key|private[_-]?key|credential)")


def redact_text(value: str) -> str:
    value = _PRIVATE_KEY.sub("[REDACTED_PRIVATE_KEY]", value)
    value = _BEARER.sub("Bearer [REDACTED]", value)
    value = _JWT.sub("[REDACTED_JWT]", value)
    value = _AWS.sub("[REDACTED_AWS_KEY]", value)
    value = _CONNECTION_SECRET.sub(r"\1[REDACTED]\2", value)
    return _LONG_TOKEN.sub("[REDACTED_TOKEN]", value)


def redact(value: Any, *, key: str = "") -> Any:
    if isinstance(value, dict):
        return {
            name: "[REDACTED]" if _SECRET_KEY.search(name) else redact(item, key=name)
            for name, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item, key=key) for item in value]
    if isinstance(value, tuple):
        return [redact(item, key=key) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def canonical_redacted_json(value: Any) -> str:
    return json.dumps(redact(value), sort_keys=True, separators=(",", ":"), default=str)


__all__ = ["canonical_redacted_json", "redact", "redact_text"]
