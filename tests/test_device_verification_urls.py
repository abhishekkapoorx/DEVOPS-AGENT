import pytest
from datetime import datetime, timezone

from agent_server.development_auth import InProcessDeviceApprovalProvider
from agent_server.postgres_device_approval import PostgresDeviceApprovalProvider
from agent_server.auth_sessions import DeviceMode


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_factory", [
    lambda: InProcessDeviceApprovalProvider("http://testserver"),
    lambda: PostgresDeviceApprovalProvider(object(), "http://testserver"),
])
async def test_verification_url_includes_user_code(provider_factory):
    provider = provider_factory()

    presentation = await provider.create_device_authorization(
        device_code="device-code",
        user_code="ABCD-2345",
        mode=DeviceMode.SIGNIN,
        expires_at=datetime.now(timezone.utc),
    )

    assert "user_code=ABCD-2345" in presentation.verification_url
