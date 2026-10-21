from __future__ import annotations

from agent_cli.auth import AuthApiError, DeviceLogin, MemoryCredentialStore, RestAuthApi, TokenResponse


class FakeAuthApi:
    def __init__(self):
        self.polls = 0
        self.rate_limit_once = False
        self.refresh_values = []
        self.logged_out = []

    def start_device(self, mode):
        assert mode == "signin"
        return {"device_code": "device-secret", "user_code": "ABCD-EFGH", "verification_url": "https://login.test/device", "expires_in": 100, "interval": 1}

    def poll_device(self, device_code):
        self.polls += 1
        assert device_code == "device-secret"
        if self.rate_limit_once:
            self.rate_limit_once = False
            raise AuthApiError(429, "slow down", retry_after=3)
        if self.polls == 1:
            return {"status": "pending", "interval": 1, "tokens": None}
        return {"status": "approved", "interval": 1, "tokens": TokenResponse(access_token="access", refresh_token="refresh-1", expires_in=900, user_id="user-7").model_dump()}

    def refresh(self, refresh_token):
        self.refresh_values.append(refresh_token)
        return TokenResponse(access_token="access-2", refresh_token="refresh-2", expires_in=900, user_id="user-7")

    def logout(self, refresh_token):
        self.logged_out.append(refresh_token)

    def current_user(self, access_token):
        return {"user_id": "user-7"}


def test_browser_device_flow_persists_only_rotating_refresh_credential():
    api = FakeAuthApi()
    store = MemoryCredentialStore()
    opened = []
    sleeps = []
    login = DeviceLogin(api=api, credentials=store, browser_opener=lambda url: opened.append(url) or False, sleep=sleeps.append)

    session = login.sign_in()
    assert session.user_id == "user-7"
    assert opened == ["https://login.test/device?user_code=ABCD-EFGH"]
    assert sleeps == [1]
    assert store.get_refresh_token() == "refresh-1"
    assert "access" not in store.get_refresh_token()


def test_restore_rotates_credential_and_logout_revokes_then_clears_local_state():
    api = FakeAuthApi()
    store = MemoryCredentialStore("old-refresh")
    login = DeviceLogin(api=api, credentials=store, browser_opener=lambda _: True, sleep=lambda _: None)

    restored = login.restore()
    assert restored.access_token == "access-2"
    assert api.refresh_values == ["old-refresh"]
    assert store.get_refresh_token() == "refresh-2"
    assert login.current_user(restored.access_token) == {"user_id": "user-7"}

    login.logout()
    assert api.logged_out == ["refresh-2"]
    assert store.get_refresh_token() is None


def test_browser_failure_shows_manual_code_and_rate_limit_is_respected():
    api = FakeAuthApi()
    api.rate_limit_once = True
    manual = []
    sleeps = []
    login = DeviceLogin(
        api=api,
        credentials=MemoryCredentialStore(),
        browser_opener=lambda _: False,
        verification_callback=lambda url, code: manual.append((url, code)),
        sleep=sleeps.append,
    )

    assert login.sign_in().user_id == "user-7"
    assert manual == [("https://login.test/device", "ABCD-EFGH")]
    assert sleeps == [3]


def test_auth_http_client_rejects_non_tls_remote_endpoint():
    import pytest

    with pytest.raises(ValueError, match="HTTPS"):
        RestAuthApi("http://api.example.test")
    assert RestAuthApi("http://localhost:8000")
    assert RestAuthApi("https://api.example.test")
