import asyncio

import pytest

from agent_server.accounts import (
    AccountAlreadyExists,
    AccountError,
    InvalidCredentials,
    LocalAccount,
    LocalAccountService,
)


class MemoryAccounts:
    def __init__(self):
        self.accounts = {}

    async def create_local_account(self, email, password_hash):
        if email in self.accounts:
            raise AccountAlreadyExists("An account with this email already exists")
        account = LocalAccount(email=email, password_hash=password_hash)
        self.accounts[email] = account
        return account

    async def get_local_account(self, email):
        return self.accounts.get(email)


def test_local_accounts_hash_passwords_and_normalize_email():
    repository = MemoryAccounts()
    service = LocalAccountService(repository)

    email = asyncio.run(service.sign_up("  Person@Example.COM ", "long-secret-passphrase"))

    account = repository.accounts[email]
    assert email == "person@example.com"
    assert account.password_hash.startswith("$argon2id$")
    assert "long-secret-passphrase" not in account.password_hash
    assert asyncio.run(service.sign_in("PERSON@example.com", "long-secret-passphrase")) == email


def test_local_accounts_reject_duplicate_emails_and_weak_passwords():
    service = LocalAccountService(MemoryAccounts())
    asyncio.run(service.sign_up("person@example.com", "long-secret-passphrase"))

    with pytest.raises(AccountAlreadyExists):
        asyncio.run(service.sign_up("PERSON@example.com", "another-long-password"))
    with pytest.raises(AccountError, match="12 and 1024"):
        asyncio.run(service.sign_up("other@example.com", "short"))
    with pytest.raises(AccountError, match="valid email"):
        asyncio.run(service.sign_up("not-an-email", "long-secret-passphrase"))
    with pytest.raises(AccountError, match="valid email"):
        asyncio.run(service.sign_up(f"{'a' * 245}@example.com", "long-secret-passphrase"))


def test_local_accounts_return_same_error_for_unknown_email_and_bad_password():
    service = LocalAccountService(MemoryAccounts())

    for email, password in (("missing@example.com", "any-password"), ("bad", "any-password")):
        with pytest.raises(InvalidCredentials, match="Invalid email or password"):
            asyncio.run(service.sign_in(email, password))
