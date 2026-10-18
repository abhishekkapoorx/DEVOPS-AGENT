from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from agent_server.observability import (
    CorrelationMetricsMiddleware,
    HttpMetrics,
    InMemoryRateLimiter,
)


def test_http_middleware_echoes_safe_correlation_id_and_tracks_low_cardinality_route():
    app = FastAPI()
    metrics = HttpMetrics()
    app.add_middleware(CorrelationMetricsMiddleware, metrics=metrics)

    @app.get("/items/{item_id}")
    def item(item_id: str):
        return {"id": item_id}

    response = TestClient(app).get(
        "/items/private-id", headers={"X-Correlation-ID": "trace-123"}
    )

    assert response.headers["x-correlation-id"] == "trace-123"
    rendered = metrics.render()
    assert 'route="/items/{item_id}"' in rendered
    assert "private-id" not in rendered


def test_rate_limiter_rejects_over_limit_and_expires_old_entries(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("agent_server.observability.time.monotonic", lambda: now[0])
    limiter = InMemoryRateLimiter(limit=1, window_seconds=10)
    limiter.check("user-1")
    with pytest.raises(HTTPException) as error:
        limiter.check("user-1")
    assert getattr(error.value, "status_code", None) == 429
    now[0] += 11
    limiter.check("user-1")
