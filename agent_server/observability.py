"""Low-cardinality HTTP metrics and correlation identifiers for the API."""

from __future__ import annotations

import logging
import re
import time
from collections import Counter, defaultdict, deque
from threading import Lock
from uuid import uuid4

from fastapi import HTTPException

logger = logging.getLogger(__name__)
_CORRELATION = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class HttpMetrics:
    def __init__(self) -> None:
        self._counts: Counter[tuple[str, str, int]] = Counter()
        self._durations: defaultdict[tuple[str, str], tuple[int, float]] = defaultdict(lambda: (0, 0.0))
        self._lock = Lock()

    def record(self, method: str, route: str, status: int, duration: float) -> None:
        key = (method, route, status)
        with self._lock:
            self._counts[key] += 1
            count, total = self._durations[(method, route)]
            self._durations[(method, route)] = (count + 1, total + duration)

    def render(self) -> str:
        with self._lock:
            counts = tuple(self._counts.items())
            durations = tuple(self._durations.items())
        lines = ["# TYPE devops_http_requests_total counter"]
        for (method, route, status), count in sorted(counts):
            lines.append(
                f'devops_http_requests_total{{method="{method}",route="{route}",status="{status}"}} {count}'
            )
        lines.append("# TYPE devops_http_request_duration_seconds summary")
        for (method, route), (count, total) in sorted(durations):
            lines.append(
                f'devops_http_request_duration_seconds_sum{{method="{method}",route="{route}"}} {total:.6f}'
            )
            lines.append(
                f'devops_http_request_duration_seconds_count{{method="{method}",route="{route}"}} {count}'
            )
        return "\n".join(lines) + "\n"


class CorrelationMetricsMiddleware:
    def __init__(self, app, *, metrics: HttpMetrics) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", ()))
        supplied = headers.get(b"x-correlation-id", b"").decode("ascii", errors="ignore")
        correlation_id = supplied if _CORRELATION.fullmatch(supplied) else uuid4().hex
        scope.setdefault("state", {})["correlation_id"] = correlation_id
        started = time.perf_counter()
        status_code = 500

        async def send_with_correlation(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = list(message.get("headers", ()))
                response_headers.append((b"x-correlation-id", correlation_id.encode("ascii")))
                message["headers"] = response_headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_correlation)
        finally:
            route = scope.get("route")
            route_template = getattr(route, "path", "/unmatched")
            duration = time.perf_counter() - started
            self.metrics.record(scope.get("method", "GET"), route_template, status_code, duration)
            logger.info(
                "http_request_complete",
                extra={
                    "event_name": "http_request_complete",
                    "correlation_id": correlation_id,
                    "http_method": scope.get("method"),
                    "http_route": route_template,
                    "http_status": status_code,
                    "duration_ms": round(duration * 1000, 2),
                },
            )


class InMemoryRateLimiter:
    """Single-process sliding-window limiter; inject a shared adapter in multi-worker deployments."""

    def __init__(self, *, limit: int = 120, window_seconds: float = 60.0) -> None:
        if limit < 1 or window_seconds <= 0:
            raise ValueError("rate limit and window must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._requests: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            requests = self._requests[key]
            while requests and requests[0] <= now - self.window_seconds:
                requests.popleft()
            if len(requests) >= self.limit:
                retry_after = max(1, int(requests[0] + self.window_seconds - now))
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded",
                    headers={"Retry-After": str(retry_after)},
                )
            requests.append(now)


__all__ = ["CorrelationMetricsMiddleware", "HttpMetrics", "InMemoryRateLimiter"]
