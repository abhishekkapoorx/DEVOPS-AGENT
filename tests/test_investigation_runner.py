from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from agent_server.investigations.evidence import ContextPack
from agent_server.investigations.runner import InvestigationRunner
from agent_server.investigations.slack import SlackPoster


class FakeSlackDestination:
    def __init__(self, urls: dict[str, str | None]) -> None:
        self.urls = urls

    async def webhook_url_for(self, owner_user_id: str) -> str | None:
        return self.urls.get(owner_user_id)


@pytest.mark.asyncio
async def test_runner_can_be_constructed_with_injected_adapters():
    runner = InvestigationRunner(lambda: None, slack=SlackPoster("https://hooks.slack.test"))

    assert runner.slack is not None
    assert runner.kube_factory is not None


@pytest.mark.asyncio
async def test_runner_resolves_slack_destination_per_investigation_owner():
    resolver = FakeSlackDestination(
        {"user-1": "https://hooks.slack.test/services/user-1", "user-2": None}
    )
    runner = InvestigationRunner(lambda: None, slack_destination=resolver)

    assert await runner._slack_webhook_url("user-1") == "https://hooks.slack.test/services/user-1"
    assert await runner._slack_webhook_url("user-2") is None
    assert await runner._slack_webhook_url("system") is None


@pytest.mark.asyncio
async def test_runner_without_integration_does_not_use_injected_poster_url():
    runner = InvestigationRunner(lambda: None, slack=SlackPoster("https://hooks.slack.test"))

    assert await runner._slack_webhook_url("user-1") == "https://hooks.slack.test"


class FakeSession:
    def __init__(self, alert, investigation) -> None:
        self.alert = alert
        self.investigation = investigation
        self.queries = 0
        self.added = []

    async def scalar(self, statement):
        self.queries += 1
        return self.alert if self.queries == 1 else self.investigation

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        return None


class FakeSessions:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return None


@pytest.mark.asyncio
async def test_runner_posts_to_owner_integration_and_skips_when_missing(monkeypatch):
    def no_tools(kube):
        return []

    async def fake_context_pack(alert, investigation_id, registry):
        return ContextPack(
            investigation_id=investigation_id,
            alertname=alert.alertname,
            namespace=alert.namespace,
            workload=alert.workload,
            severity=alert.severity,
            summary=alert.summary,
        )

    monkeypatch.setattr("agent_server.investigations.runner.default_kubernetes_tools", no_tools)
    monkeypatch.setattr("agent_server.investigations.runner.build_context_pack", fake_context_pack)

    calls = []

    class RecordingPoster:
        def __init__(self, webhook_url):
            self.webhook_url = webhook_url

        async def post_text(self, message):
            calls.append((self.webhook_url, message))
            return True

    monkeypatch.setattr("agent_server.investigations.runner.SlackPoster", RecordingPoster)

    async def no_kube():
        return object()

    def make_investigation(owner):
        now = datetime.now(timezone.utc)
        alert = SimpleNamespace(
            source="alertmanager",
            source_fingerprint="fp",
            alertname="KubeContainerOOMKilled",
            severity="critical",
            status="firing",
            namespace="boutique",
            workload="recommendationservice",
            pod="pod-1",
            summary="memory pressure",
            description="container restarted",
            labels={},
            annotations={},
            started_at=now,
            ended_at=None,
            received_at=now,
            raw={},
        )
        investigation = SimpleNamespace(
            id=f"inv-{owner}",
            owner_user_id=owner,
            occurrence_count=1,
            slack_posted_at=None,
            status="pending",
        )
        session = FakeSession(alert, investigation)
        return investigation, FakeSessions(session), session

    investigation, sessions, session = make_investigation("user-1")
    runner = InvestigationRunner(
        sessions,
        kube_factory=no_kube,
        slack_destination=FakeSlackDestination({"user-1": "https://hooks.slack.test/user-1"}),
    )
    await runner(investigation)

    assert calls[0][0] == "https://hooks.slack.test/user-1"
    assert session.investigation.slack_posted_at is not None
    assert any(getattr(row, "action", None) == "slack_posted" for row in session.added)

    investigation, sessions, session = make_investigation("user-2")
    runner = InvestigationRunner(
        sessions,
        kube_factory=no_kube,
        slack_destination=FakeSlackDestination({}),
    )
    await runner(investigation)

    assert len(calls) == 1
    assert session.investigation.slack_posted_at is None
    assert any(getattr(row, "action", None) == "slack_skipped" for row in session.added)
