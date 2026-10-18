"""REST client for conversations and durable Agent Run progress."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Mapping, Protocol
from uuid import uuid4


class RestApiError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


class HttpResponse(Protocol):
    status: int
    headers: Mapping[str, str]

    def read(self) -> bytes: ...
    def readline(self) -> bytes: ...
    def close(self) -> None: ...


Opener = Callable[..., HttpResponse]


class RestAgentClient:
    """Create conversations, submit idempotent messages, and replay run events."""

    def __init__(
        self,
        base_url: str,
        *,
        access_token: Callable[[], str],
        refresh_access_token: Callable[[], str | None],
        opener: Opener = urllib.request.urlopen,
        timeout: float = 30.0,
        max_reconnects: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not base_url.startswith("https://") and not _is_loopback(base_url):
            raise ValueError("Agent REST API requires HTTPS outside localhost")
        if timeout <= 0 or max_reconnects < 0:
            raise ValueError("timeout must be positive and reconnect count non-negative")
        self.base_url = base_url.rstrip("/")
        self._access_token = access_token()
        self.refresh_access_token = refresh_access_token
        self.opener = opener
        self.timeout = timeout
        self.max_reconnects = max_reconnects
        self.sleep = sleep
        self._correlation_id = ""
        self._traceparent = ""

    def ask(
        self,
        message: str,
        *,
        conversation_id: str | None = None,
        idempotency_key: str | None = None,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if not message.strip():
            raise ValueError("message must not be empty")
        trace_id = uuid4().hex
        self._correlation_id = trace_id
        self._traceparent = f"00-{trace_id}-{uuid4().hex[:16]}-01"
        if conversation_id is None:
            conversation = self._json_request(
                "POST", "/v1/conversations", {"title": message[:200] or "New conversation"}
            )
            conversation_id = str(conversation["id"])
        turn = self._json_request(
            "POST",
            f"/v1/conversations/{urllib.parse.quote(conversation_id, safe='')}/messages",
            {"content": message},
            headers={"Idempotency-Key": idempotency_key or uuid4().hex},
        )
        if turn.get("status") in {"completed", "failed", "cancelled", "expired"}:
            return turn
        run_id = str(turn["run_id"])
        last_sequence = 0
        for attempt in range(self.max_reconnects + 1):
            try:
                last_sequence = self._read_event_stream(run_id, last_sequence, on_event)
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                if attempt >= self.max_reconnects:
                    raise RestApiError(503, "Unable to reconnect to Agent Run events") from error
                self.sleep(min(0.25 * (2**attempt), 2.0))
            state = self._json_request("GET", f"/v1/runs/{urllib.parse.quote(run_id, safe='')}")
            if state.get("status") in {"completed", "failed", "cancelled", "expired"}:
                if state.get("status") != "completed":
                    raise RestApiError(502, str(state.get("error") or "Agent Run failed"))
                return state
        raise RestApiError(503, "Agent Run is still in progress; reconnect and replay its events")

    def list_conversations(self) -> list[dict[str, Any]]:
        response = self._json_request("GET", "/v1/conversations")
        if not isinstance(response, list) or any(not isinstance(item, dict) for item in response):
            raise RestApiError(502, "Agent API returned an invalid conversation list")
        return response

    def create_conversation(self, title: str = "New conversation") -> dict[str, Any]:
        response = self._json_request("POST", "/v1/conversations", {"title": title[:200]})
        if not isinstance(response, dict) or not isinstance(response.get("id"), str):
            raise RestApiError(502, "Agent API returned an invalid conversation")
        return response

    def list_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        path = f"/v1/conversations/{urllib.parse.quote(conversation_id, safe='')}/messages"
        response = self._json_request("GET", path)
        if not isinstance(response, list) or any(not isinstance(item, dict) for item in response):
            raise RestApiError(502, "Agent API returned an invalid message list")
        return response

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        response = self._json_request(
            "DELETE", f"/v1/runs/{urllib.parse.quote(run_id, safe='')}"
        )
        if not isinstance(response, dict):
            raise RestApiError(502, "Agent API returned an invalid cancellation response")
        return response

    def _read_event_stream(
        self,
        run_id: str,
        after: int,
        on_event: Callable[[dict[str, Any]], None] | None,
    ) -> int:
        query = urllib.parse.urlencode({"after": after})
        path = f"/v1/runs/{urllib.parse.quote(run_id, safe='')}/events/stream?{query}"
        request = self._request("GET", path, token=self._access_token)
        try:
            response = self._open(request)
        except urllib.error.HTTPError as error:
            if error.code != 401 or not self._refresh_token():
                raise _api_error(error) from error
            request = self._request("GET", path, token=self._access_token)
            response = self._open(request)
        sequence = after
        event_sequence: int | None = None
        event_type = "message"
        data_lines: list[str] = []
        try:
            while True:
                line = response.readline()
                if not line:
                    break
                decoded = line.decode("utf-8").rstrip("\r\n")
                if not decoded:
                    if data_lines:
                        data = json.loads("\n".join(data_lines))
                        if event_type in {"created", "running", "resumed", "completed", "failed"}:
                            delivered_sequence = event_sequence
                            if delivered_sequence is None:
                                delivered_sequence = int(data.get("sequence", sequence))
                        event = {"type": event_type, "run_id": run_id, "data": data}
                        if on_event:
                            if event_type == "completed" and data.get("message"):
                                on_event(
                                    {
                                        "type": "agent_message",
                                        "message": str(data["message"]),
                                        "final": True,
                                    }
                                )
                            else:
                                on_event(event)
                        if event_type in {"created", "running", "resumed", "completed", "failed"}:
                            sequence = max(sequence, delivered_sequence)
                        if event_type == "completed":
                            return sequence
                        if event_type == "failed":
                            return sequence
                    event_type = "message"
                    event_sequence = None
                    data_lines = []
                elif decoded.startswith("id:"):
                    try:
                        event_sequence = int(decoded[3:].strip())
                    except ValueError:
                        continue
                elif decoded.startswith("event:"):
                    event_type = decoded[6:].strip()
                elif decoded.startswith("data:"):
                    data_lines.append(decoded[5:].lstrip())
        finally:
            response.close()
        return sequence

    def _json_request(
        self,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        token = self._access_token
        for attempt in range(2):
            request = self._request(method, path, body, headers=headers, token=token)
            try:
                response = self._open(request)
            except urllib.error.HTTPError as error:
                if error.code == 401 and attempt == 0:
                    refreshed = self.refresh_access_token()
                    if refreshed:
                        self._access_token = token = refreshed
                        continue
                raise _api_error(error) from error
            try:
                if response.status == 204:
                    return {}
                data = json.loads(response.read())
                if not isinstance(data, (dict, list)):
                    raise RestApiError(502, "Agent API returned an invalid response")
                return data
            finally:
                response.close()
        raise RestApiError(401, "Access token expired")

    def _refresh_token(self) -> bool:
        refreshed = self.refresh_access_token()
        if not refreshed:
            return False
        self._access_token = refreshed
        return True

    def _open(self, request):
        try:
            return self.opener(request, timeout=self.timeout)
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError):
            raise

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, object] | None = None,
        *,
        headers: Mapping[str, str] | None = None,
        token: str | None = None,
    ):
        payload = None if body is None else json.dumps(body).encode("utf-8")
        request_headers = {"Accept": "application/json"}
        if self._correlation_id:
            request_headers["X-Correlation-ID"] = self._correlation_id
        if self._traceparent:
            request_headers["traceparent"] = self._traceparent
        if payload is not None:
            request_headers["Content-Type"] = "application/json"
        if token:
            request_headers["Authorization"] = f"Bearer {token}"
        request_headers.update(headers or {})
        if path.endswith("/events/stream"):
            request_headers["Accept"] = "text/event-stream"
        return urllib.request.Request(
            self.base_url + path, data=payload, headers=request_headers, method=method
        )


def _api_error(error: urllib.error.HTTPError) -> RestApiError:
    try:
        payload = json.loads(error.read(2048))
        detail = payload.get("detail", "Agent API request failed")
    except (ValueError, TypeError):
        detail = "Agent API request failed"
    return RestApiError(error.code, str(detail))


def _is_loopback(base_url: str) -> bool:
    parsed = urllib.parse.urlsplit(base_url)
    return parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}


__all__ = ["RestAgentClient", "RestApiError"]
