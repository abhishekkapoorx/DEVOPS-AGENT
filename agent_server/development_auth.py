"""Explicitly local-only browser approval provider for development.

This is deliberately not an identity provider.  It exists so a developer can
exercise the device flow without a separate account web site.  Deployment
composition only enables it when ``DEVOPS_AGENT_AUTH_MODE=development``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from .auth_sessions import DeviceApproval, DeviceMode, DevicePresentation


@dataclass(frozen=True)
class PendingApproval:
    user_code: str
    mode: DeviceMode
    expires_at: datetime


class DevelopmentApprovalProvider:
    """In-process approval store exposed only by the development API route."""

    def __init__(self, verification_base_url: str) -> None:
        self._base_url = verification_base_url.rstrip("/")
        self._pending: dict[str, PendingApproval] = {}
        self._decisions: dict[str, DeviceApproval] = {}

    async def create_device_authorization(
        self, *, device_code: str, user_code: str, mode: DeviceMode, expires_at: datetime
    ) -> DevicePresentation:
        approval_id = uuid4().hex
        self._pending[approval_id] = PendingApproval(user_code, mode, expires_at)
        return DevicePresentation(
            approval_id=approval_id,
            verification_url=f"{self._base_url}/v1/development/device/{approval_id}",
        )

    async def get_device_approval(self, approval_id: str) -> DeviceApproval | None:
        return self._decisions.get(approval_id)

    def pending(self, approval_id: str) -> PendingApproval | None:
        return self._pending.get(approval_id)

    def decide(self, approval_id: str, *, user_code: str, user_id: str, approved: bool) -> bool:
        pending = self._pending.get(approval_id)
        if pending is None or pending.user_code != user_code or pending.expires_at <= datetime.now(pending.expires_at.tzinfo):
            return False
        self._decisions[approval_id] = DeviceApproval(
            status="approved" if approved else "denied",
            user_id=user_id if approved else None,
        )
        return True


__all__ = ["DevelopmentApprovalProvider"]
