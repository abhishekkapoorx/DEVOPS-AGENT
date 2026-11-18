"""Authenticated encryption for user-managed provider secrets."""

from __future__ import annotations

import base64
import os
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecretConfigurationError(RuntimeError):
    pass


class SecretBox:
    """AES-256-GCM adapter with an environment-held master key."""

    def __init__(self, key: bytes, *, key_version: str = "v1") -> None:
        if len(key) != 32:
            raise SecretConfigurationError("ENCRYPTION_KEY must decode to exactly 32 bytes")
        self._key = key
        self.key_version = key_version

    @classmethod
    def from_environment(cls) -> "SecretBox":
        encoded = os.getenv("ENCRYPTION_KEY", "")
        if not encoded:
            raise SecretConfigurationError("ENCRYPTION_KEY is required for secret management")
        try:
            key = base64.b64decode(encoded, validate=True)
        except Exception as error:
            raise SecretConfigurationError("ENCRYPTION_KEY must be valid base64") from error
        return cls(key)

    def encrypt(self, plaintext: str, *, associated_data: str) -> tuple[bytes, bytes]:
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(self._key).encrypt(nonce, plaintext.encode("utf-8"), associated_data.encode())
        return ciphertext, nonce

    def decrypt(self, ciphertext: bytes, nonce: bytes, *, associated_data: str) -> str:
        plaintext = AESGCM(self._key).decrypt(nonce, ciphertext, associated_data.encode())
        return plaintext.decode("utf-8")


__all__ = ["SecretBox", "SecretConfigurationError"]
