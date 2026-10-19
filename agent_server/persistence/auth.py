"""PostgreSQL persistence for device grants and rotating refresh sessions."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from agent_server.accounts import AccountAlreadyExists, LocalAccount
from agent_server.auth_sessions import AuthSession, DeviceAuthorization, DeviceMode, DeviceStatus
from .postgres import Base

AuthBase = Base


class DeviceAuthorizationRow(AuthBase):
    __tablename__ = "auth_device_authorizations"

    device_code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    approval_id: Mapped[str] = mapped_column(String(255), index=True)
    mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    next_poll_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approval_status: Mapped[str | None] = mapped_column(String(16))
    approved_user_id: Mapped[str | None] = mapped_column(String(255))


class AuthSessionRow(AuthBase):
    __tablename__ = "auth_sessions"

    session_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[str] = mapped_column(String(255), index=True)
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by: Mapped[str | None] = mapped_column(String(32))


class LocalAccountRow(AuthBase):
    __tablename__ = "auth_accounts"

    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PostgresAuthRepository:
    """Repository that stores only hashed bearer codes and refresh tokens."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create_local_account(self, email: str, password_hash: str) -> LocalAccount:
        row = LocalAccountRow(
            email=email,
            password_hash=password_hash,
            created_at=datetime.now(timezone.utc),
        )
        try:
            async with self._sessions() as session:
                session.add(row)
                await session.commit()
        except IntegrityError as error:
            raise AccountAlreadyExists("An account with this email already exists") from error
        return LocalAccount(email=row.email, password_hash=row.password_hash)

    async def get_local_account(self, email: str) -> LocalAccount | None:
        async with self._sessions() as session:
            row = await session.get(LocalAccountRow, email)
        return LocalAccount(email=row.email, password_hash=row.password_hash) if row else None

    async def create_device(self, device: DeviceAuthorization) -> None:
        async with self._sessions() as session:
            session.add(_device_row(device))
            await session.commit()

    async def get_device(self, device_code: str) -> DeviceAuthorization | None:
        async with self._sessions() as session:
            row = await session.get(DeviceAuthorizationRow, _hash(device_code))
        return _device(row, device_code) if row else None

    async def get_device_approval_request(self, approval_id: str):
        async with self._sessions() as session:
            return await session.scalar(
                select(DeviceAuthorizationRow).where(
                    DeviceAuthorizationRow.approval_id == approval_id
                )
            )

    async def get_device_approval(self, approval_id: str):
        from agent_server.auth_sessions import DeviceApproval

        row = await self.get_device_approval_request(approval_id)
        if row is None or row.approval_status is None:
            return None
        return DeviceApproval(
            status=DeviceStatus(row.approval_status), user_id=row.approved_user_id
        )

    async def decide_device_approval(
        self, approval_id: str, user_code: str, user_id: str | None, approved: bool
    ) -> bool:
        now = datetime.now(timezone.utc)
        async with self._sessions() as session:
            result = await session.execute(
                update(DeviceAuthorizationRow)
                .where(
                    DeviceAuthorizationRow.approval_id == approval_id,
                    DeviceAuthorizationRow.user_code == user_code,
                    DeviceAuthorizationRow.status == DeviceStatus.PENDING.value,
                    DeviceAuthorizationRow.expires_at > now,
                    DeviceAuthorizationRow.approval_status.is_(None),
                )
                .values(
                    approval_status=(DeviceStatus.APPROVED if approved else DeviceStatus.DENIED).value,
                    approved_user_id=user_id if approved else None,
                )
            )
            await session.commit()
        return result.rowcount == 1

    async def update_device(self, device: DeviceAuthorization) -> None:
        async with self._sessions() as session:
            await session.execute(
                update(DeviceAuthorizationRow)
                .where(DeviceAuthorizationRow.device_code_hash == _hash(device.device_code))
                .values(
                    status=device.status.value,
                    next_poll_at=device.next_poll_at,
                    consumed_at=device.consumed_at,
                )
            )
            await session.commit()

    async def complete_device(self, device: DeviceAuthorization, auth_session: AuthSession) -> bool:
        """Atomically consume one pending device grant and create its first session."""
        async with self._sessions() as session:
            async with session.begin():
                row = await session.scalar(
                    select(DeviceAuthorizationRow)
                    .where(
                        DeviceAuthorizationRow.device_code_hash == _hash(device.device_code),
                        DeviceAuthorizationRow.status == DeviceStatus.PENDING.value,
                        DeviceAuthorizationRow.expires_at > device.consumed_at,
                    )
                    .with_for_update()
                )
                if row is None:
                    return False
                row.status = DeviceStatus.CONSUMED.value
                row.consumed_at = device.consumed_at
                row.next_poll_at = device.next_poll_at
                session.add(_session_row(auth_session))
        return True

    async def get_session_by_refresh_hash(self, token_hash: str) -> AuthSession | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(AuthSessionRow).where(AuthSessionRow.refresh_hash == token_hash)
            )
        return _auth_session(row) if row else None

    async def rotate_session(
        self, old: AuthSession, replacement: AuthSession, at: datetime
    ) -> bool:
        """Perform refresh rotation under a row lock to serialize concurrent replays."""
        async with self._sessions() as session:
            async with session.begin():
                row = await session.scalar(
                    select(AuthSessionRow)
                    .where(AuthSessionRow.session_id == old.session_id)
                    .with_for_update()
                )
                if (
                    row is None
                    or row.refresh_hash != old.refresh_hash
                    or row.revoked_at is not None
                    or row.replaced_by is not None
                    or row.expires_at <= at
                ):
                    return False
                row.revoked_at = at
                row.replaced_by = replacement.session_id
                session.add(_session_row(replacement))
        return True

    async def revoke_session_family(self, family_id: str, at: datetime) -> None:
        async with self._sessions() as session:
            await session.execute(
                update(AuthSessionRow)
                .where(AuthSessionRow.family_id == family_id, AuthSessionRow.revoked_at.is_(None))
                .values(revoked_at=at)
            )
            await session.commit()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _device_row(value: DeviceAuthorization) -> DeviceAuthorizationRow:
    return DeviceAuthorizationRow(
        device_code_hash=_hash(value.device_code),
        user_code=value.user_code,
        approval_id=value.approval_id,
        mode=value.mode,
        status=value.status.value,
        created_at=value.created_at,
        expires_at=value.expires_at,
        next_poll_at=value.next_poll_at,
        consumed_at=value.consumed_at,
        approval_status=None,
        approved_user_id=None,
    )


def _device(row: DeviceAuthorizationRow, device_code: str) -> DeviceAuthorization:
    return DeviceAuthorization(
        device_code=device_code,
        user_code=row.user_code,
        approval_id=row.approval_id,
        mode=DeviceMode(row.mode),
        status=DeviceStatus(row.status),
        created_at=row.created_at,
        expires_at=row.expires_at,
        next_poll_at=row.next_poll_at,
        consumed_at=row.consumed_at,
    )


def _session_row(value: AuthSession) -> AuthSessionRow:
    return AuthSessionRow(**value.model_dump())


def _auth_session(row: AuthSessionRow) -> AuthSession:
    return AuthSession.model_validate(
        {column.name: getattr(row, column.name) for column in AuthSessionRow.__table__.columns}
    )


__all__ = ["AuthBase", "AuthSessionRow", "DeviceAuthorizationRow", "LocalAccountRow", "PostgresAuthRepository"]
