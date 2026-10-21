"""PostgreSQL-backed browser approval bridge for the CLI device flow."""

from __future__ import annotations

from uuid import uuid4

from .auth_sessions import DeviceApproval, DeviceMode, DevicePresentation
from .development_auth import PendingApproval


class PostgresDeviceApprovalProvider:
    """Store account approval decisions on the durable device authorization row."""

    def __init__(self, repository, verification_base_url: str) -> None:
        self.repository = repository
        self._base_url = verification_base_url.rstrip("/")

    async def create_device_authorization(
        self, *, device_code: str, user_code: str, mode: DeviceMode, expires_at
    ) -> DevicePresentation:
        approval_id = uuid4().hex
        return DevicePresentation(
            approval_id=approval_id,
            verification_url=f"{self._base_url}/v1/auth/device/verify/{approval_id}",
        )

    async def pending(self, approval_id: str) -> PendingApproval | None:
        row = await self.repository.get_device_approval_request(approval_id)
        if row is None:
            return None
        return PendingApproval(row.user_code, DeviceMode(row.mode), row.expires_at)

    async def decide(
        self, approval_id: str, *, user_code: str, user_id: str, approved: bool
    ) -> bool:
        return await self.repository.decide_device_approval(
            approval_id, user_code, user_id, approved
        )

    async def get_device_approval(self, approval_id: str) -> DeviceApproval | None:
        return await self.repository.get_device_approval(approval_id)


__all__ = ["PostgresDeviceApprovalProvider"]
