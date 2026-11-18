import httpx
import pytest

from agent_server.investigations.evidence import ContextPack, Evidence
from agent_server.investigations.slack import SlackPoster, build_deterministic_briefing


def _pack():
    return ContextPack(
        investigation_id="i",
        alertname="KubeContainerOOMKilled",
        namespace="boutique",
        workload="recommendationservice",
        severity="critical",
        summary="memory pressure",
        evidence=[
            Evidence(
                id="ev-oom",
                investigation_id="i",
                source="kubernetes.pod_status",
                query="pod/recommendationservice",
                fetched_at="2026-11-15T09:00:00Z",
                summary="last terminated reason OOMKilled",
                raw_ref="evidence:i:pod",
            )
        ],
    )


def test_deterministic_briefing_contains_evidence_ids_and_read_only_footer():
    briefing = build_deterministic_briefing(_pack())

    assert "[ev-oom]" in briefing
    assert "Deterministic context pack" in briefing
    assert "READ-ONLY analysis. No actions were taken." in briefing


@pytest.mark.asyncio
async def test_slack_poster_retries_rate_limit_and_posts_payload():
    calls = []
    delays = []

    async def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(200, json={"ok": True})

    async_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def record_delay(delay):
        delays.append(delay)

    poster = SlackPoster(
        "https://hooks.slack.test",
        client_factory=lambda: async_client,
        sleep=record_delay,
    )

    assert await poster.post(_pack()) is True
    assert len(calls) == 2
    assert delays == [3.0]
    assert "ev-oom" in calls[1].content.decode()
    await async_client.aclose()


@pytest.mark.asyncio
async def test_unset_slack_webhook_logs_fallback_and_returns_false(caplog):
    caplog.set_level("INFO")
    poster = SlackPoster("")

    assert await poster.post(_pack()) is False
    assert "deterministic briefing" in caplog.text


@pytest.mark.asyncio
async def test_slack_briefing_is_size_limited():
    async def handler(request):
        assert len(request.content) < 40_000
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    pack = _pack()
    pack.evidence[0].summary = "x" * 100_000
    poster = SlackPoster("https://hooks.slack.test", client_factory=lambda: client)

    assert await poster.post(pack) is True
    await client.aclose()
