"""Browser device authorization and durable refresh-session lifecycle."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Callable, Protocol
from uuid import uuid4

from pydantic import BaseModel

from .auth import issue_access_token, verify_access_token


class DeviceStatus(StrEnum):
    PENDING = "pending"
    DENIED = "denied"
    APPROVED = "approved"
    EXPIRED = "expired"
    CONSUMED = "consumed"


class DeviceMode(StrEnum):
    SIGNIN = "signin"
    SIGNUP = "signup"


class AuthError(Exception):
    """Expected authentication state or credential error."""


class DeviceRateLimited(AuthError):
    """The caller polled sooner than the advertised interval."""


class DeviceAuthorization(BaseModel):
    device_code: str
    user_code: str
    approval_id: str
    mode: DeviceMode
    status: DeviceStatus
    created_at: datetime
    expires_at: datetime
    next_poll_at: datetime
    consumed_at: datetime | None = None


class DeviceApproval(BaseModel):
    status: DeviceStatus = DeviceStatus.APPROVED
    user_id: str | None = None
    email: str | None = None
    display_name: str | None = None


class AuthenticatedUser(BaseModel):
    user_id: str
    scopes: frozenset[str] = frozenset()


class DevicePresentation(BaseModel):
    approval_id: str
    verification_url: str


class AuthSession(BaseModel):
    session_id: str
    family_id: str
    user_id: str
    refresh_hash: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    replaced_by: str | None = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str


class DeviceStart(BaseModel):
    device_code: str
    user_code: str
    verification_url: str
    expires_in: int
    interval: int


class DevicePoll(BaseModel):
    status: DeviceStatus
    tokens: TokenPair | None = None
    interval: int


class WebsiteApprovalProvider(Protocol):
    """Trusted website boundary: creates approval UX and returns verified identity."""

    async def create_device_authorization(
        self, *, device_code: str, user_code: str, mode: DeviceMode, expires_at: datetime
    ) -> DevicePresentation: ...

    async def get_device_approval(self, approval_id: str) -> DeviceApproval | None: ...


class AuthRepository(Protocol):
    async def create_device(self, device: DeviceAuthorization) -> None: ...
    async def get_device(self, device_code: str) -> DeviceAuthorization | None: ...
    async def update_device(self, device: DeviceAuthorization) -> None: ...
    async def create_session(self, session: AuthSession) -> None: ...
    async def get_session_by_refresh_hash(self, token_hash: str) -> AuthSession | None: ...
    async def complete_device(self, device: DeviceAuthorization, session: AuthSession) -> bool: ...
    async def rotate_session(self, old: AuthSession, replacement: AuthSession, at: datetime) -> bool: ...
    async def revoke_session_family(self, family_id: str, at: datetime) -> None: ...


class AuthSessionService:
    def __init__(
        self,
        *,
        repository: AuthRepository,
        approval_provider: WebsiteApprovalProvider,
        access_token_secret: str,
        device_ttl: int = 600,
        poll_interval: int = 5,
        refresh_ttl: int = 60 * 60 * 24 * 30,
        access_ttl: int = 900,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if not access_token_secret:
            raise ValueError("access token secret is required")
        self.repository = repository
        self.approval_provider = approval_provider
        self.access_token_secret = access_token_secret
        self.device_ttl = device_ttl
        self.poll_interval = poll_interval
        self.refresh_ttl = refresh_ttl
        self.access_ttl = access_ttl
        self.now = now

    async def start_device(self, mode: DeviceMode | str) -> DeviceStart:
        try:
            mode = DeviceMode(mode)
        except ValueError as error:
            raise ValueError("mode must be signin or signup") from error
        now = self.now()
        device_code = secrets.token_urlsafe(32)
        user_code = _user_code()
        expires_at = now + timedelta(seconds=self.device_ttl)
        presentation = await self.approval_provider.create_device_authorization(
            device_code=device_code,
            user_code=user_code,
            mode=mode,
            expires_at=expires_at,
        )
        device = DeviceAuthorization(
            device_code=device_code,
            user_code=user_code,
            approval_id=presentation.approval_id,
            mode=mode,
            status=DeviceStatus.PENDING,
            created_at=now,
            expires_at=expires_at,
            next_poll_at=now,
        )
        await self.repository.create_device(device)
        return DeviceStart(
            device_code=device_code,
            user_code=user_code,
            verification_url=presentation.verification_url,
            expires_in=self.device_ttl,
            interval=self.poll_interval,
        )

    async def poll_device(self, device_code: str) -> DevicePoll:
        now = self.now()
        device = await self.repository.get_device(device_code)
        if device is None:
            raise AuthError("invalid device authorization")
        if device.status in {DeviceStatus.CONSUMED, DeviceStatus.DENIED, DeviceStatus.EXPIRED}:
            return DevicePoll(status=device.status, interval=self.poll_interval)
        if device.expires_at <= now:
            expired = device.model_copy(update={"status": DeviceStatus.EXPIRED})
            await self.repository.update_device(expired)
            return DevicePoll(status=DeviceStatus.EXPIRED, interval=self.poll_interval)
        if device.next_poll_at > now:
            raise DeviceRateLimited("polling too quickly")

        approval = await self.approval_provider.get_device_approval(device.approval_id)
        changed = device.model_copy(update={"next_poll_at": now + timedelta(seconds=self.poll_interval)})
        if approval is None or approval.status is DeviceStatus.PENDING:
            await self.repository.update_device(changed)
            return DevicePoll(status=DeviceStatus.PENDING, interval=self.poll_interval)
        if approval.status is DeviceStatus.DENIED:
            changed = changed.model_copy(update={"status": DeviceStatus.DENIED})
            await self.repository.update_device(changed)
            return DevicePoll(status=DeviceStatus.DENIED, interval=self.poll_interval)
        if approval.status is not DeviceStatus.APPROVED or not approval.user_id:
            raise AuthError("approval provider returned no verified identity")

        refresh = secrets.token_urlsafe(48)
        family_id = uuid4().hex
        session = AuthSession(
            session_id=uuid4().hex,
            family_id=family_id,
            user_id=approval.user_id,
            refresh_hash=_hash_token(refresh),
            created_at=now,
            expires_at=now + timedelta(seconds=self.refresh_ttl),
        )
        consumed = changed.model_copy(update={"status": DeviceStatus.CONSUMED, "consumed_at": now})
        if not await self.repository.complete_device(consumed, session):
            return DevicePoll(status=DeviceStatus.CONSUMED, interval=self.poll_interval)
        return DevicePoll(
            status=DeviceStatus.APPROVED,
            interval=self.poll_interval,
            tokens=self._tokens(session.user_id, refresh),
        )

    async def refresh(self, refresh_token: str) -> TokenPair:
        if not refresh_token:
            raise AuthError("invalid refresh token")
        now = self.now()
        session = await self.repository.get_session_by_refresh_hash(_hash_token(refresh_token))
        if session is None:
            raise AuthError("invalid refresh token")
        if session.revoked_at is not None or session.replaced_by is not None:
            await self.repository.revoke_session_family(session.family_id, now)
            raise AuthError("refresh token reuse detected; session family revoked")
        if session.expires_at <= now:
            raise AuthError("refresh session expired")

        new_refresh = secrets.token_urlsafe(48)
        replacement = AuthSession(
            session_id=uuid4().hex,
            family_id=session.family_id,
            user_id=session.user_id,
            refresh_hash=_hash_token(new_refresh),
            created_at=now,
            expires_at=now + timedelta(seconds=self.refresh_ttl),
        )
        if not await self.repository.rotate_session(session, replacement, now):
            latest = await self.repository.get_session_by_refresh_hash(_hash_token(refresh_token))
            if latest is not None and (latest.revoked_at is not None or latest.replaced_by is not None):
                await self.repository.revoke_session_family(latest.family_id, now)
                raise AuthError("refresh token reuse detected; session family revoked")
            raise AuthError("refresh session expired or revoked")
        return self._tokens(session.user_id, new_refresh)

    async def logout(self, refresh_token: str) -> None:
        session = await self.repository.get_session_by_refresh_hash(_hash_token(refresh_token))
        if session is not None:
            await self.repository.revoke_session_family(session.family_id, self.now())

    def current_user(self, access_token: str, *, claimed_user_id: str | None = None) -> AuthenticatedUser | None:
        claims = verify_access_token(access_token, self.access_token_secret)
        if claims is None or (claimed_user_id is not None and claimed_user_id != claims.user_id):
            return None
        return AuthenticatedUser(user_id=claims.user_id, scopes=claims.scopes)

    def _tokens(self, user_id: str, refresh_token: str) -> TokenPair:
        return TokenPair(
            access_token=issue_access_token(self.access_token_secret, user_id, self.access_ttl),
            refresh_token=refresh_token,
            expires_in=self.access_ttl,
            user_id=user_id,
        )


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _user_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(4)) + "-" + "".join(
        secrets.choice(alphabet) for _ in range(4)
    )


__all__ = [
    "AuthError", "AuthRepository", "AuthSession", "AuthSessionService", "AuthenticatedUser", "DeviceApproval",
    "DeviceAuthorization", "DeviceMode", "DevicePoll", "DevicePresentation", "DeviceRateLimited",
    "DeviceStart", "DeviceStatus", "TokenPair", "WebsiteApprovalProvider",
]
