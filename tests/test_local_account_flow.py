from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_server.accounts import AccountAlreadyExists, LocalAccount, LocalAccountService
from agent_server.api.auth_routes import create_auth_router
from agent_server.auth_sessions import AuthSessionService, DeviceApproval, DeviceStatus
from agent_server.deployment import _mount_local_account_approval
from agent_server.postgres_device_approval import PostgresDeviceApprovalProvider


class MemoryRepository:
    def __init__(self):
        self.accounts = {}
        self.devices = {}
        self.sessions = {}
        self.approvals = {}

    async def create_local_account(self, email, password_hash):
        if email in self.accounts:
            raise AccountAlreadyExists("An account with this email already exists")
        self.accounts[email] = LocalAccount(email, password_hash)
        return self.accounts[email]

    async def get_local_account(self, email):
        return self.accounts.get(email)

    async def create_device(self, device):
        self.devices[device.device_code] = device

    async def get_device(self, device_code):
        return self.devices.get(device_code)

    async def update_device(self, device):
        self.devices[device.device_code] = device

    async def get_device_approval_request(self, approval_id):
        device = next((item for item in self.devices.values() if item.approval_id == approval_id), None)
        if device is None:
            return None
        decision = self.approvals.get(approval_id)
        return SimpleNamespace(
            user_code=device.user_code,
            mode=device.mode.value,
            expires_at=device.expires_at,
            approval_status=decision.status.value if decision else None,
            approved_user_id=decision.user_id if decision else None,
        )

    async def get_device_approval(self, approval_id):
        row = await self.get_device_approval_request(approval_id)
        if row is None or row.approval_status is None:
            return None
        return DeviceApproval(status=row.approval_status, user_id=row.approved_user_id)

    async def decide_device_approval(self, approval_id, user_code, user_id, approved):
        row = await self.get_device_approval_request(approval_id)
        if row is None or row.user_code != user_code or row.approval_status is not None:
            return False
        self.approvals[approval_id] = DeviceApproval(
            status=DeviceStatus.APPROVED if approved else DeviceStatus.DENIED,
            user_id=user_id if approved else None,
        )
        return True

    async def complete_device(self, device, session):
        if self.devices[device.device_code].status is not DeviceStatus.PENDING:
            return False
        self.devices[device.device_code] = device
        self.sessions[session.session_id] = session
        return True

    async def get_session_by_refresh_hash(self, token_hash):
        return next((item for item in self.sessions.values() if item.refresh_hash == token_hash), None)

    async def rotate_session(self, old, replacement, at):
        return False

    async def revoke_session_family(self, family_id, at):
        return None


def test_browser_signup_signin_and_current_identity():
    repository = MemoryRepository()
    provider = PostgresDeviceApprovalProvider(repository, "http://testserver")
    service = AuthSessionService(
        repository=repository,
        approval_provider=provider,
        access_token_secret="this-is-a-long-test-secret-value",
        poll_interval=0,
    )
    app = FastAPI()
    app.include_router(create_auth_router(service))
    _mount_local_account_approval(app, provider, LocalAccountService(repository))

    with TestClient(app) as client:
        started = client.post("/v1/auth/device", json={"mode": "signup"}).json()
        page = client.get(started["verification_url"].replace("http://testserver", ""), params={"user_code": started["user_code"]})
        assert page.status_code == 200
        assert "name='email'" in page.text
        approved = client.post(
            page.url.path,
            data={"user_code": started["user_code"], "email": "Person@Example.com", "password": "a-long-test-password"},
        )
        assert approved.status_code == 200
        # A new provider instance can recover the approval from the durable repository.
        service.approval_provider = PostgresDeviceApprovalProvider(repository, "http://testserver")
        tokens = client.post("/v1/auth/device/poll", json={"device_code": started["device_code"]}).json()["tokens"]
        assert tokens["user_id"] == "person@example.com"
        identity = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert identity.json() == {"user_id": "person@example.com"}

        duplicate = client.post("/v1/auth/device", json={"mode": "signup"}).json()
        page = client.get(duplicate["verification_url"].replace("http://testserver", ""), params={"user_code": duplicate["user_code"]})
        rejected = client.post(
            page.url.path,
            data={"user_code": duplicate["user_code"], "email": "person@example.com", "password": "a-long-test-password"},
        )
        assert rejected.status_code == 409

        signin = client.post("/v1/auth/device", json={"mode": "signin"}).json()
        page = client.get(signin["verification_url"].replace("http://testserver", ""), params={"user_code": signin["user_code"]})
        signed_in = client.post(
            page.url.path,
            data={"user_code": signin["user_code"], "email": "PERSON@example.com", "password": "a-long-test-password"},
        )
        assert signed_in.status_code == 200
        signed_in_tokens = client.post("/v1/auth/device/poll", json={"device_code": signin["device_code"]}).json()["tokens"]
        assert signed_in_tokens["user_id"] == "person@example.com"


def test_signin_device_page_can_switch_to_signup_without_restarting_device_flow():
    repository = MemoryRepository()
    provider = PostgresDeviceApprovalProvider(repository, "http://testserver")
    service = AuthSessionService(
        repository=repository,
        approval_provider=provider,
        access_token_secret="this-is-a-long-test-secret-value",
        poll_interval=0,
    )
    app = FastAPI()
    app.include_router(create_auth_router(service))
    _mount_local_account_approval(app, provider, LocalAccountService(repository))

    with TestClient(app) as client:
        started = client.post("/v1/auth/device", json={"mode": "signin"}).json()
        path = started["verification_url"].replace("http://testserver", "")
        signup_page = client.get(path, params={"user_code": started["user_code"], "mode": "signup"})
        assert signup_page.status_code == 200
        assert "Create your account" in signup_page.text
        assert "name='mode' value='signup'" in signup_page.text

        approved = client.post(
            path,
            data={
                "user_code": started["user_code"],
                "mode": "signup",
                "email": "new-user@example.com",
                "password": "a-long-test-password",
            },
        )
        assert approved.status_code == 200
        tokens = client.post("/v1/auth/device/poll", json={"device_code": started["device_code"]}).json()["tokens"]
        assert tokens["user_id"] == "new-user@example.com"
