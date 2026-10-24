"""Local helper that receives authenticated tool requests and runs them here."""

from __future__ import annotations

import argparse
import json
import platform as host_platform
import time
import sys
import uuid
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .auth import DeviceLogin, RestAuthApi, SystemCredentialStore
from .executor import LocalToolExecutor


class LocalToolService:
    def __init__(self, api_url: str, *, workspace: str | None = None, approval_ipc: bool = False) -> None:
        self.api_url = api_url.rstrip("/")
        self.auth = DeviceLogin(api=RestAuthApi(api_url), credentials=SystemCredentialStore())
        self.approval_ipc = approval_ipc
        self.executor = LocalToolExecutor(approval_callback=self._approve, workspace=workspace)

    def _approve(self, name: str, arguments: dict[str, Any], _operation) -> bool:
        if self.approval_ipc:
            request_id = uuid.uuid4().hex
            print(json.dumps({
                "type": "approval_request", "request_id": request_id,
                "name": name, "arguments": arguments,
            }), flush=True)
            response = sys.stdin.readline()
            try:
                return bool(json.loads(response).get("approved"))
            except (ValueError, AttributeError):
                return False
        print(f"\nTool request: {name} {json.dumps(arguments, sort_keys=True)}", flush=True)
        try:
            answer = input("Allow this command? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return answer in {"y", "yes"}

    def serve(self) -> None:
        client_platform = _client_platform()
        while True:
            tokens = self.auth.restore()
            if tokens is None:
                time.sleep(2)
                continue
            request = urllib.request.Request(
                self.api_url + "/v1/local-tools/stream",
                headers={
                    "Authorization": f"Bearer {tokens.access_token}",
                    "Accept": "text/event-stream",
                    "X-Local-Platform": client_platform,
                    "X-Local-Workspace": urllib.parse.quote(str(self.executor.workspace), safe=""),
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    data_lines: list[str] = []
                    while line := response.readline():
                        decoded = line.decode("utf-8").rstrip("\r\n")
                        if not decoded:
                            if data_lines:
                                payload = json.loads("\n".join(data_lines))
                                self._handle(payload)
                            data_lines = []
                        elif decoded.startswith("data:"):
                            data_lines.append(decoded[5:].lstrip())
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
                if self.approval_ipc:
                    print(json.dumps({
                        "type": "helper_error",
                        "message": str(error)[:500],
                    }), flush=True)
                else:
                    print(f"Local tool connection interrupted: {error}", file=sys.stderr, flush=True)
                time.sleep(1)

    def _handle(self, payload: dict[str, Any]) -> None:
        name = str(payload.get("name", ""))
        arguments = payload.get("arguments")
        result = self.executor.execute(
            name,
            arguments,
            request_id=str(payload.get("call_id", "")),
        ).to_dict()
        result_body = {
            "exit_code": int(result.get("exit_code", 1)),
            "stdout": str(result.get("stdout", "")),
            "stderr": str(result.get("stderr", "")),
            "duration_ms": float(result.get("duration_ms", 0)),
        }
        self._post_result(str(payload.get("call_id", "")), result_body)

    def _post_result(self, call_id: str, body: dict[str, Any]) -> None:
        encoded_id = urllib.parse.quote(call_id, safe="")
        for attempt in range(2):
            tokens = self.auth.restore()
            if tokens is None:
                raise RuntimeError("Local helper is no longer signed in")
            request = urllib.request.Request(
                f"{self.api_url}/v1/local-tools/{encoded_id}/result",
                data=json.dumps(body).encode("utf-8"),
                headers={"Authorization": f"Bearer {tokens.access_token}", "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    response.read()
                return
            except urllib.error.HTTPError as error:
                if error.code == 401 and attempt == 0:
                    continue
                summary = _http_error_summary(error)
                raise urllib.error.URLError(
                    f"HTTP {error.code} submitting tool result: {summary}"
                ) from error


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local DevOps Agent tool helper")
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--approval-ipc", action="store_true")
    args = parser.parse_args()
    LocalToolService(args.api_url, approval_ipc=args.approval_ipc).serve()
    return 0


def _client_platform() -> str:
    system = host_platform.system().lower()
    if system == "linux":
        return "linux"
    if system == "windows":
        return "windows"
    return "other"


def _http_error_summary(error: urllib.error.HTTPError) -> str:
    """Report validation locations without echoing tool output or request data."""
    try:
        payload = json.loads(error.read(4_096).decode("utf-8"))
    except (OSError, UnicodeError, ValueError):
        return "server rejected the result; response details unavailable"
    details = payload.get("detail") if isinstance(payload, dict) else None
    if not isinstance(details, list):
        return "server rejected the result; response details omitted"
    issues = []
    for item in details[:8]:
        if not isinstance(item, dict):
            continue
        location = ".".join(str(part) for part in item.get("loc", ()))
        kind = str(item.get("type", "validation_error"))
        issues.append(f"{location or 'result'} ({kind})")
    return "; ".join(issues) if issues else "server rejected the result; response details omitted"


if __name__ == "__main__":
    raise SystemExit(main())
