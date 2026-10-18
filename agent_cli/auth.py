"""Browser-based sign-in and secure local refresh-session management."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Callable, Protocol

from pydantic import BaseModel


class AuthApiError(Exception):
    def __init__(self, status_code: int, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class DeviceChallenge(BaseModel):
    device_code: str
    user_code: str
    verification_url: str
    expires_in: int
    interval: int


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user_id: str
    token_type: str = "bearer"


class DevicePollResponse(BaseModel):
    status: str
    interval: int
    tokens: TokenResponse | None = None


class CredentialStore(Protocol):
    def get_refresh_token(self) -> str | None: ...
    def set_refresh_token(self, token: str) -> None: ...
    def delete_refresh_token(self) -> None: ...


class AuthApi(Protocol):
    def start_device(self, mode: str) -> dict[str, object]: ...
    def poll_device(self, device_code: str) -> dict[str, object]: ...
    def refresh(self, refresh_token: str) -> TokenResponse: ...
    def logout(self, refresh_token: str) -> None: ...
    def current_user(self, access_token: str) -> dict[str, str]: ...


class MemoryCredentialStore:
    """In-memory credential store for tests and short-lived embedding only."""

    def __init__(self, refresh_token: str | None = None) -> None:
        self._refresh_token = refresh_token

    def get_refresh_token(self) -> str | None:
        return self._refresh_token

    def set_refresh_token(self, token: str) -> None:
        self._refresh_token = token

    def delete_refresh_token(self) -> None:
        self._refresh_token = None


class ProtectedFileCredentialStore:
    """OS-user-protected fallback: DPAPI on Windows, owner-only file on POSIX."""

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            if os.name == "nt":
                base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
            else:
                base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
            path = base / "devops-agent" / "credentials.bin"
        self.path = path

    def get_refresh_token(self) -> str | None:
        try:
            payload = self.path.read_bytes()
        except FileNotFoundError:
            return None
        if os.name == "nt":
            payload = _dpapi(payload, protect=False)
        else:
            self.path.chmod(0o600)
        return json.loads(payload.decode("utf-8"))["refresh_token"]

    def set_refresh_token(self, token: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self.path.parent.chmod(0o700)
        payload = json.dumps({"refresh_token": token}, separators=(",", ":")).encode()
        if os.name == "nt":
            payload = _dpapi(payload, protect=True)
            self.path.write_bytes(payload)
        else:
            descriptor = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                os.fchmod(descriptor, 0o600)
                with os.fdopen(descriptor, "wb", closefd=False) as stream:
                    stream.write(payload)
            finally:
                os.close(descriptor)

    def delete_refresh_token(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


class SystemCredentialStore:
    """Use a working OS keyring backend, falling back to protected local storage."""

    def __init__(self, fallback: CredentialStore | None = None) -> None:
        self._fallback = fallback or ProtectedFileCredentialStore()
        self._keyring = None
        try:
            import keyring

            backend = keyring.get_keyring()
            if backend.priority > 0:
                self._keyring = keyring
        except Exception:
            self._keyring = None

    def get_refresh_token(self) -> str | None:
        if self._keyring:
            return self._keyring.get_password("devops-agent", "refresh-token")
        return self._fallback.get_refresh_token()

    def set_refresh_token(self, token: str) -> None:
        if self._keyring:
            self._keyring.set_password("devops-agent", "refresh-token", token)
        else:
            self._fallback.set_refresh_token(token)

    def delete_refresh_token(self) -> None:
        if self._keyring:
            try:
                self._keyring.delete_password("devops-agent", "refresh-token")
            except self._keyring.errors.PasswordDeleteError:
                pass
        else:
            self._fallback.delete_refresh_token()


class RestAuthApi:
    """Small synchronous HTTP adapter for bounded authentication requests."""

    def __init__(self, base_url: str, *, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        parsed = urllib.parse.urlsplit(self.base_url)
        local_hosts = {"localhost", "127.0.0.1", "::1"}
        if not parsed.hostname or (
            parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in local_hosts)
        ):
            raise ValueError("authentication API must use HTTPS (HTTP is allowed only for localhost)")

    def start_device(self, mode: str) -> dict[str, object]:
        return self._request("POST", "/v1/auth/device", {"mode": mode})

    def poll_device(self, device_code: str) -> dict[str, object]:
        return self._request("POST", "/v1/auth/device/poll", {"device_code": device_code})

    def refresh(self, refresh_token: str) -> TokenResponse:
        return TokenResponse.model_validate(self._request("POST", "/v1/auth/refresh", {"refresh_token": refresh_token}))

    def logout(self, refresh_token: str) -> None:
        self._request("POST", "/v1/auth/logout", {"refresh_token": refresh_token})

    def current_user(self, access_token: str) -> dict[str, str]:
        return self._request("GET", "/v1/auth/me", token=access_token)

    def _request(
        self, method: str, path: str, body: dict[str, object] | None = None, *, token: str | None = None
    ) -> dict[str, object]:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(self.base_url + path, data=payload, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if response.status == 204:
                    return {}
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            detail = error.read(2048).decode("utf-8", errors="replace")
            retry_after = error.headers.get("Retry-After")
            try:
                retry_after_seconds = float(retry_after) if retry_after is not None else None
            except ValueError:
                retry_after_seconds = None
            raise AuthApiError(
                error.code,
                detail or "Authentication request failed",
                retry_after=retry_after_seconds,
            ) from error


class DeviceLogin:
    """Coordinates browser approval, polling, refresh, logout, and identity lookup."""

    def __init__(
        self,
        *,
        api: AuthApi,
        credentials: CredentialStore,
        browser_opener: Callable[[str], bool] = webbrowser.open,
        verification_callback: Callable[[str, str], None] = lambda url, code: None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.api = api
        self.credentials = credentials
        self.browser_opener = browser_opener
        self.verification_callback = verification_callback
        self.sleep = sleep
        self.monotonic = monotonic

    def sign_in(self) -> TokenResponse:
        return self._device_flow("signin")

    def sign_up(self) -> TokenResponse:
        return self._device_flow("signup")

    def _device_flow(self, mode: str) -> TokenResponse:
        challenge = DeviceChallenge.model_validate(self.api.start_device(mode))
        separator = "&" if "?" in challenge.verification_url else "?"
        url = challenge.verification_url + separator + urllib.parse.urlencode({"user_code": challenge.user_code})
        try:
            opened = self.browser_opener(url)
        except Exception:
            opened = False
        if not opened:
            self.verification_callback(challenge.verification_url, challenge.user_code)
        deadline = self.monotonic() + challenge.expires_in
        interval = challenge.interval
        while self.monotonic() < deadline:
            try:
                response = self.api.poll_device(challenge.device_code)
            except AuthApiError as error:
                if error.status_code != 429:
                    raise
                self.sleep(max(interval, error.retry_after or 0))
                continue
            result = DevicePollResponse.model_validate(response)
            if result.status == "approved" and result.tokens is not None:
                self.credentials.set_refresh_token(result.tokens.refresh_token)
                return result.tokens
            if result.status in {"denied", "expired", "consumed"}:
                raise AuthApiError(401, f"Device authorization {result.status}")
            interval = max(interval, result.interval)
            if result.status == "pending":
                self.sleep(interval)
        raise AuthApiError(408, "Device authorization expired before approval")

    def restore(self) -> TokenResponse | None:
        refresh_token = self.credentials.get_refresh_token()
        if refresh_token is None:
            return None
        try:
            result = self.api.refresh(refresh_token)
        except AuthApiError as error:
            if error.status_code == 401:
                self.credentials.delete_refresh_token()
                return None
            raise
        self.credentials.set_refresh_token(result.refresh_token)
        return result

    def logout(self) -> None:
        refresh_token = self.credentials.get_refresh_token()
        try:
            if refresh_token is not None:
                self.api.logout(refresh_token)
        finally:
            self.credentials.delete_refresh_token()

    def current_user(self, access_token: str) -> dict[str, str]:
        return self.api.current_user(access_token)


def _dpapi(payload: bytes, *, protect: bool) -> bytes:
    """Encrypt/decrypt bytes for the current Windows user using DPAPI."""

    class DataBlob(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    source_buffer = ctypes.create_string_buffer(payload)
    source = DataBlob(len(payload), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = DataBlob()
    if protect:
        success = crypt32.CryptProtectData(ctypes.byref(source), "DevOps Agent", None, None, None, 1, ctypes.byref(target))
    else:
        success = crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    if not success:
        raise OSError(ctypes.get_last_error(), "Windows user credential protection failed")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel32.LocalFree(target.pbData)


__all__ = [
    "AuthApiError", "CredentialStore", "DeviceChallenge", "DeviceLogin", "DevicePollResponse",
    "MemoryCredentialStore", "ProtectedFileCredentialStore", "RestAuthApi", "SystemCredentialStore",
    "TokenResponse",
]
