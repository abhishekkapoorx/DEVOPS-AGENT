from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from agent_server.auth_sessions import AuthSessionService, DeviceApproval, DeviceRateLimited, DeviceStatus


class MemoryAuthRepository:
    def __init__(self):
        self.devices = {}
        self.sessions = {}

    async def create_device(self, device):
        self.devices[device.device_code] = device

    async def get_device(self, device_code):
        return self.devices.get(device_code)

    async def update_device(self, device):
        self.devices[device.device_code] = device

    async def get_session_by_refresh_hash(self, token_hash):
        return next((s for s in self.sessions.values() if s.refresh_hash == token_hash), None)

    async def complete_device(self, device, session):
        current = self.devices.get(device.device_code)
        if current is None or current.status is not DeviceStatus.PENDING:
            return False
        self.devices[device.device_code] = device
        self.sessions[session.session_id] = session
        return True

    async def rotate_session(self, old, replacement, at):
        current = self.sessions.get(old.session_id)
        if current is None or current.revoked_at is not None or current.replaced_by is not None:
            return False
        self.sessions[old.session_id] = current.model_copy(
            update={"revoked_at": at, "replaced_by": replacement.session_id}
        )
        self.sessions[replacement.session_id] = replacement
        return True

    async def revoke_session_family(self, family_id, at):
        for key, session in self.sessions.items():
            if session.family_id == family_id:
                self.sessions[key] = session.model_copy(update={"revoked_at": at})


class WebsiteApproval:
    def __init__(self):
        self.approvals = {}
        self.presentations = {}

    async def create_device_authorization(self, *, device_code, user_code, mode, expires_at):
        from agent_server.auth_sessions import DevicePresentation

        approval_id = f"approval-{device_code}"
        self.presentations[approval_id] = (user_code, mode, expires_at)
        return DevicePresentation(
            approval_id=approval_id,
            verification_url="https://example.test/device",
        )

    async def get_device_approval(self, approval_id):
        return self.approvals.get(approval_id)

    async def get_approval(self, approval_id):
        return self.approvals.get(approval_id)


def run(coro):
    return asyncio.run(coro)


def make_service():
    repository = MemoryAuthRepository()
    website = WebsiteApproval()
    service = AuthSessionService(
        repository=repository,
        approval_provider=website,
        access_token_secret="test-secret-that-is-not-used-in-production",
        device_ttl=60,
        poll_interval=1,
        now=lambda: datetime.now(timezone.utc),
    )
    return service, repository, website


def test_device_flow_waits_for_explicit_website_approval_and_completes_once():
    service, repository, website = make_service()

    started = run(service.start_device("signup"))
    assert started.verification_url == "https://example.test/device"
    pending = run(service.poll_device(started.device_code))
    assert pending.status is DeviceStatus.PENDING
    device = repository.devices[started.device_code]
    repository.devices[started.device_code] = device.model_copy(
        update={"next_poll_at": datetime.now(timezone.utc) - timedelta(seconds=1)}
    )

    device = repository.devices[started.device_code]
    website.approvals[device.approval_id] = DeviceApproval(
        user_id="user-42", email="person@example.test", display_name="Person"
    )
    completed = run(service.poll_device(started.device_code))
    assert completed.status is DeviceStatus.APPROVED
    assert completed.tokens.user_id == "user-42"
    assert completed.tokens.refresh_token
    assert run(service.poll_device(started.device_code)).status is DeviceStatus.CONSUMED


def test_refresh_rotates_token_and_reuse_revokes_entire_session_family():
    service, repository, website = make_service()
    started = run(service.start_device("signin"))
    device = repository.devices[started.device_code]
    repository.devices[started.device_code] = device.model_copy(
        update={"next_poll_at": datetime.now(timezone.utc) - timedelta(seconds=1)}
    )
    website.approvals[device.approval_id] = DeviceApproval(user_id="user-42")
    issued = run(service.poll_device(started.device_code)).tokens

    rotated = run(service.refresh(issued.refresh_token))
    assert rotated.refresh_token != issued.refresh_token
    with pytest.raises(Exception, match="revoked|reuse"):
        run(service.refresh(issued.refresh_token))
    with pytest.raises(Exception, match="revoked|reuse"):
        run(service.refresh(rotated.refresh_token))


def test_logout_revokes_refresh_session_and_current_user_comes_from_access_claims():
    service, repository, website = make_service()
    started = run(service.start_device("signin"))
    device = repository.devices[started.device_code]
    repository.devices[started.device_code] = device.model_copy(
        update={"next_poll_at": datetime.now(timezone.utc) - timedelta(seconds=1)}
    )
    website.approvals[device.approval_id] = DeviceApproval(user_id="verified-user")
    issued = run(service.poll_device(started.device_code)).tokens

    assert service.current_user(issued.access_token).user_id == "verified-user"
    assert service.current_user(issued.access_token, claimed_user_id="attacker") is None
    run(service.logout(issued.refresh_token))
    with pytest.raises(Exception, match="revoked|invalid"):
        run(service.refresh(issued.refresh_token))


def test_device_flow_rejects_unknown_mode_and_expires():
    service, repository, website = make_service()
    with pytest.raises(ValueError, match="mode"):
        run(service.start_device("password"))

    started = run(service.start_device("signin"))
    device = repository.devices[started.device_code]
    repository.devices[started.device_code] = device.model_copy(
        update={"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}
    )
    assert run(service.poll_device(started.device_code)).status is DeviceStatus.EXPIRED


def test_device_polling_is_rate_limited_and_denials_are_terminal():
    service, repository, website = make_service()
    started = run(service.start_device("signin"))
    assert run(service.poll_device(started.device_code)).status is DeviceStatus.PENDING
    with pytest.raises(DeviceRateLimited):
        run(service.poll_device(started.device_code))

    device = repository.devices[started.device_code]
    repository.devices[started.device_code] = device.model_copy(
        update={"next_poll_at": datetime.now(timezone.utc) - timedelta(seconds=1)}
    )
    website.approvals[device.approval_id] = DeviceApproval(status=DeviceStatus.DENIED)
    assert run(service.poll_device(started.device_code)).status is DeviceStatus.DENIED
    assert run(service.poll_device(started.device_code)).status is DeviceStatus.DENIED
