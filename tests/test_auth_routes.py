from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_server.api.auth_routes import create_auth_router
from agent_server.auth_sessions import DeviceApproval, DevicePresentation
from tests.test_auth_sessions import MemoryAuthRepository


class Website:
    def __init__(self):
        self.approvals = {}

    async def create_device_authorization(self, *, device_code, user_code, mode, expires_at):
        return DevicePresentation(approval_id="website-approval", verification_url="https://login.test/device")

    async def get_device_approval(self, approval_id):
        return self.approvals.get(approval_id)


def test_device_signin_refresh_logout_and_current_user_contract():
    from agent_server.auth_sessions import AuthSessionService

    repository = MemoryAuthRepository()
    website = Website()
    service = AuthSessionService(repository=repository, approval_provider=website, access_token_secret="test-secret")
    app = FastAPI()
    app.include_router(create_auth_router(service))
    client = TestClient(app)

    started = client.post("/v1/auth/device", json={"mode": "signin"})
    assert started.status_code == 200
    assert started.json()["verification_url"] == "https://login.test/device"
    device_code = started.json()["device_code"]
    website.approvals["website-approval"] = DeviceApproval(user_id="trusted-user")
    device = repository.devices[device_code]
    repository.devices[device_code] = device.model_copy(update={"next_poll_at": datetime.now(timezone.utc)})
    completed = client.post("/v1/auth/device/poll", json={"device_code": device_code, "user_id": "attacker"})
    assert completed.status_code == 200
    credentials = completed.json()["tokens"]
    assert credentials["user_id"] == "trusted-user"

    me = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {credentials['access_token']}"})
    assert me.json() == {"user_id": "trusted-user"}
    assert client.get("/v1/auth/me", headers={"Authorization": f"Bearer {credentials['access_token']}"}, params={"user_id": "attacker"}).json() == {"user_id": "trusted-user"}

    refreshed = client.post("/v1/auth/refresh", json={"refresh_token": credentials["refresh_token"]})
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != credentials["refresh_token"]
    assert client.post("/v1/auth/logout", json={"refresh_token": refreshed.json()["refresh_token"]}).status_code == 204
    assert client.post("/v1/auth/refresh", json={"refresh_token": refreshed.json()["refresh_token"]}).status_code == 401


def test_current_user_rejects_missing_or_invalid_access_token():
    from agent_server.auth_sessions import AuthSessionService

    service = AuthSessionService(repository=MemoryAuthRepository(), approval_provider=Website(), access_token_secret="test-secret")
    app = FastAPI()
    app.include_router(create_auth_router(service))
    response = TestClient(app).get("/v1/auth/me")
    assert response.status_code == 401
