"""Agent Runtime HTTP adapter for the remote Tool Service."""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Any, Callable

from agent_core.tools import ToolExecutionContext, ToolResult


class ToolServiceError(RuntimeError):
    pass


class RestToolServiceClient:
    """Submit bounded Tool Calls over HTTPS using stable idempotency keys."""

    def __init__(
        self,
        base_url: str,
        *,
        access_token: Callable[[ToolExecutionContext], str],
        timeout: float = 30.0,
        opener: Callable[..., Any] = urllib.request.urlopen,
        allow_insecure_http: bool = False,
    ) -> None:
        if (
            not base_url.startswith("https://")
            and not _is_loopback(base_url)
            and not allow_insecure_http
        ):
            raise ValueError("Tool Service requires HTTPS outside localhost")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout = timeout
        self.opener = opener

    async def execute(
        self, *, name: str, version: str, arguments: dict[str, Any], context: ToolExecutionContext
    ) -> ToolResult:
        return await asyncio.to_thread(
            self._execute, name=name, version=version, arguments=arguments, context=context
        )

    def _execute(self, *, name, version, arguments, context) -> ToolResult:
        if not context.idempotency_key:
            raise ValueError("Tool Calls require an idempotency key")
        payload = json.dumps(
            {
                "run_id": context.run_id,
                "call_id": context.call_id,
                "name": name,
                "version": version,
                "arguments": arguments,
            }
        ).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.access_token(context)}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Idempotency-Key": context.idempotency_key,
            "X-Correlation-ID": context.correlation_id or context.run_id,
        }
        if context.traceparent:
            headers["traceparent"] = context.traceparent
        request = urllib.request.Request(
            f"{self.base_url}/v1/tool-calls", data=payload, headers=headers, method="POST"
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                body = json.loads(response.read(128_000))
        except urllib.error.HTTPError as error:
            raise ToolServiceError(f"Tool Service returned HTTP {error.code}") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise ToolServiceError("Tool Service request failed") from error
        try:
            return ToolResult(
                call_id=str(body["call_id"]),
                name=str(body["name"]),
                status=body["status"],
                output=body.get("output", {}),
                error=body.get("error"),
                duration_ms=float(body.get("duration_ms", 0)),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ToolServiceError("Tool Service returned an invalid response") from error


def _is_loopback(base_url: str) -> bool:
    from urllib.parse import urlsplit

    parsed = urlsplit(base_url)
    return parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}


__all__ = ["RestToolServiceClient", "ToolServiceError"]
