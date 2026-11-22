"""User secret adapters and one-time webhook credential management."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agent_server.persistence.postgres import IntegrationRow, UserSecretRow, WebhookSecretRow
from agent_server.secrets import SecretBox


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SecretRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], secret_box: SecretBox) -> None:
        self._sessions = sessions
        self._box = secret_box

    async def create_webhook_secret(self, user_id: str, name: str) -> tuple[WebhookSecretRow, str]:
        raw = f"whsec_{secrets.token_urlsafe(32)}"
        row = WebhookSecretRow(
            id=uuid4().hex,
            user_id=user_id,
            name=name,
            secret_hash=_hash_secret(raw),
            created_at=datetime.now(timezone.utc),
        )
        async with self._sessions() as session:
            session.add(row)
            await session.commit()
        return row, raw

    async def list_webhook_secrets(self, user_id: str) -> list[WebhookSecretRow]:
        async with self._sessions() as session:
            return list(
                (
                    await session.scalars(
                        select(WebhookSecretRow)
                        .where(WebhookSecretRow.user_id == user_id, WebhookSecretRow.revoked_at.is_(None))
                        .order_by(WebhookSecretRow.created_at.desc())
                    )
                ).all()
            )

    async def revoke_webhook_secret(self, user_id: str, secret_id: str) -> bool:
        async with self._sessions() as session:
            result = await session.execute(
                update(WebhookSecretRow)
                .where(
                    WebhookSecretRow.id == secret_id,
                    WebhookSecretRow.user_id == user_id,
                    WebhookSecretRow.revoked_at.is_(None),
                )
                .values(revoked_at=datetime.now(timezone.utc))
            )
            await session.commit()
            return result.rowcount == 1

    async def find_webhook_owner(self, raw_secret: str) -> str | None:
        digest = _hash_secret(raw_secret)
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(WebhookSecretRow).where(WebhookSecretRow.revoked_at.is_(None))
                )
            ).all()
            for row in rows:
                if hmac.compare_digest(row.secret_hash, digest):
                    row.last_used_at = datetime.now(timezone.utc)
                    await session.commit()
                    return row.user_id
        return None

    async def save_resource_secret(self, user_id: str, provider: str, name: str, plaintext: str) -> UserSecretRow:
        associated_data = f"{user_id}:{provider}:{name}"
        ciphertext, nonce = self._box.encrypt(plaintext, associated_data=associated_data)
        async with self._sessions() as session:
            row = await session.scalar(
                select(UserSecretRow).where(
                    UserSecretRow.user_id == user_id,
                    UserSecretRow.provider == provider,
                    UserSecretRow.name == name,
                )
            )
            if row is None:
                row = UserSecretRow(
                    id=uuid4().hex,
                    user_id=user_id,
                    provider=provider,
                    name=name,
                    ciphertext=ciphertext,
                    nonce=nonce,
                    key_version=self._box.key_version,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(row)
            else:
                row.ciphertext = ciphertext
                row.nonce = nonce
                row.key_version = self._box.key_version
                row.updated_at = datetime.now(timezone.utc)
            await session.commit()
            return row

    async def list_resource_secrets(self, user_id: str) -> list[UserSecretRow]:
        async with self._sessions() as session:
            return list(
                (
                    await session.scalars(
                        select(UserSecretRow)
                        .where(UserSecretRow.user_id == user_id)
                        .order_by(UserSecretRow.updated_at.desc())
                    )
                ).all()
            )

    async def delete_resource_secret(self, user_id: str, secret_id: str) -> bool:
        async with self._sessions() as session:
            row = await session.scalar(
                select(UserSecretRow).where(
                    UserSecretRow.id == secret_id,
                    UserSecretRow.user_id == user_id,
                )
            )
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True


    async def save_integration(
        self,
        owner_user_id: str,
        provider: str,
        display_name: str,
        webhook_url: str,
        enabled: bool,
    ) -> IntegrationRow:
        now = datetime.now(timezone.utc)
        async with self._sessions() as session:
            row = await session.scalar(
                select(IntegrationRow).where(
                    IntegrationRow.owner_user_id == owner_user_id,
                    IntegrationRow.provider == provider,
                )
            )
            if row is None:
                row = IntegrationRow(
                    id=uuid4().hex,
                    owner_user_id=owner_user_id,
                    provider=provider,
                    created_at=now,
                )
                session.add(row)
            ciphertext, nonce = self._box.encrypt(
                webhook_url, associated_data=f"{owner_user_id}:{provider}:{row.id}"
            )
            row.display_name = display_name
            row.enabled = enabled
            row.webhook_url_ciphertext = ciphertext
            row.webhook_url_nonce = nonce
            row.key_version = self._box.key_version
            row.updated_at = now
            await session.commit()
            return row

    async def list_integrations(self, owner_user_id: str) -> list[IntegrationRow]:
        async with self._sessions() as session:
            return list(
                (
                    await session.scalars(
                        select(IntegrationRow)
                        .where(IntegrationRow.owner_user_id == owner_user_id)
                        .order_by(IntegrationRow.provider, IntegrationRow.display_name)
                    )
                ).all()
            )

    async def get_integration(self, owner_user_id: str, provider: str) -> IntegrationRow | None:
        async with self._sessions() as session:
            return await session.scalar(
                select(IntegrationRow).where(
                    IntegrationRow.owner_user_id == owner_user_id,
                    IntegrationRow.provider == provider,
                )
            )

    async def decrypt_integration_webhook_url(self, row: IntegrationRow) -> str:
        return self._box.decrypt(
            row.webhook_url_ciphertext,
            row.webhook_url_nonce,
            associated_data=f"{row.owner_user_id}:{row.provider}:{row.id}",
        )

    async def delete_integration(self, owner_user_id: str, provider: str) -> bool:
        async with self._sessions() as session:
            row = await session.scalar(
                select(IntegrationRow).where(
                    IntegrationRow.owner_user_id == owner_user_id,
                    IntegrationRow.provider == provider,
                )
            )
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}****{value[-4:]}"


__all__ = ["SecretRepository", "mask_secret"]
