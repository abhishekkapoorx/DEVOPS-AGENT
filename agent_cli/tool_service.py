"""Local helper that receives authenticated tool requests and runs them here."""

from __future__ import annotations

import argparse
import json
import time
import sys
import uuid
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .auth import DeviceLogin, RestAuthApi, SystemCredentialStore
from .executor import CommandExecutor, ExecutionRequest


class LocalToolService:
    def __init__(self, api_url: str, *, workspace: str | None = None, approval_ipc: bool = False) -> None:
        self.api_url = api_url.rstrip("/")
        self.auth = DeviceLogin(api=RestAuthApi(api_url), credentials=SystemCredentialStore())
        self.approval_ipc = approval_ipc
        self.executor = CommandExecutor(approval_callback=self._approve, workspace=workspace)

    def _approve(self, request: ExecutionRequest, _operation) -> bool:
        if self.approval_ipc:
            request_id = uuid.uuid4().hex
            print(json.dumps({
                "type": "approval_request", "request_id": request_id,
                "tool": request.tool, "args": list(request.args),
            }), flush=True)
            response = sys.stdin.readline()
            try:
                return bool(json.loads(response).get("approved"))
            except (ValueError, AttributeError):
                return False
        print(f"\nTool request: {request.tool} {' '.join(request.args)}", flush=True)
        try:
            answer = input("Allow this command? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        return answer in {"y", "yes"}

    def serve(self) -> None:
        while True:
            tokens = self.auth.restore()
            if tokens is None:
                time.sleep(2)
                continue
            request = urllib.request.Request(
                self.api_url + "/v1/local-tools/stream",
                headers={"Authorization": f"Bearer {tokens.access_token}", "Accept": "text/event-stream"},
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
                print(f"Local tool connection interrupted: {error}", flush=True)
                time.sleep(1)

    def _handle(self, payload: dict[str, Any]) -> None:
        tool = str(payload.get("name", "")).partition(".")[0]
        arguments = payload.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        try:
            result = self.executor.execute(
                ExecutionRequest(tool=tool, args=tuple(arguments.get("argv", ())), cwd=arguments.get("cwd")),
                request_id=str(payload.get("call_id", "")),
            ).to_dict()
        except (ValueError, OSError) as error:
            result = {"exit_code": 1, "stdout": "", "stderr": str(error), "duration_ms": 0}
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
                raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local DevOps Agent tool helper")
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--approval-ipc", action="store_true")
    args = parser.parse_args()
    LocalToolService(args.api_url, approval_ipc=args.approval_ipc).serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
