"""Self-hosted email/password accounts for the local web approval flow."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Protocol

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError


_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MAX_EMAIL_LENGTH = 254


@dataclass(frozen=True)
class LocalAccount:
    email: str
    password_hash: str


class LocalAccountRepository(Protocol):
    async def create_local_account(self, email: str, password_hash: str) -> LocalAccount: ...
    async def get_local_account(self, email: str) -> LocalAccount | None: ...


class AccountError(ValueError):
    """Expected account validation or credential failure."""


class AccountAlreadyExists(AccountError):
    """The normalized email address is already registered."""


class InvalidCredentials(AccountError):
    """Email/password pair is invalid; deliberately does not identify which."""


class LocalAccountService:
    """Validate credentials and persist only Argon2id password hashes."""

    def __init__(self, repository: LocalAccountRepository, *, hasher: PasswordHasher | None = None):
        self.repository = repository
        self.hasher = hasher or PasswordHasher()
        # Verify an equivalent-cost dummy hash when an email is not registered,
        # reducing the response-time difference between unknown email and bad password.
        self._dummy_hash = self.hasher.hash("not-a-real-account-password")

    async def sign_up(self, email: str, password: str) -> str:
        normalized = _normalize_email(email)
        if len(password) < 12 or len(password) > 1024:
            raise AccountError("Password must be between 12 and 1024 characters")
        password_hash = await asyncio.to_thread(self.hasher.hash, password)
        try:
            await self.repository.create_local_account(normalized, password_hash)
        except AccountAlreadyExists:
            raise
        return normalized

    async def sign_in(self, email: str, password: str) -> str:
        try:
            normalized = _normalize_email(email)
        except AccountError:
            normalized = ""
        if not password or len(password) > 1024:
            raise InvalidCredentials("Invalid email or password")
        account = await self.repository.get_local_account(normalized) if normalized else None
        encoded = account.password_hash if account else self._dummy_hash
        try:
            valid = await asyncio.to_thread(self.hasher.verify, encoded, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            valid = False
        if account is None or not valid:
            raise InvalidCredentials("Invalid email or password")
        return account.email


def _normalize_email(email: str) -> str:
    normalized = email.strip().casefold()
    if len(normalized) > _MAX_EMAIL_LENGTH or not _EMAIL.fullmatch(normalized):
        raise AccountError("Enter a valid email address")
    return normalized


__all__ = [
    "AccountAlreadyExists",
    "AccountError",
    "InvalidCredentials",
    "LocalAccount",
    "LocalAccountRepository",
    "LocalAccountService",
]
