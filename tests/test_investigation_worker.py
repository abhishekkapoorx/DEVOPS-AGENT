from datetime import datetime, timezone

import pytest

from agent_server.investigations.worker import backoff_seconds
from agent_server.persistence.postgres import InvestigationRow


@pytest.mark.parametrize(
    ("attempt", "expected"),
    [(1, 1), (2, 2), (3, 4), (8, 128), (12, 300)],
)
def test_worker_backoff_is_bounded(attempt, expected):
    assert backoff_seconds(attempt) == expected


@pytest.mark.asyncio
async def test_worker_shutdown_event_is_observed():
    from agent_server.investigations.worker import InvestigationWorker

    worker = InvestigationWorker(lambda: None, poll_seconds=0)
    stopping = __import__("asyncio").Event()
    stopping.set()

    await worker.run_forever(stopping)


@pytest.mark.asyncio
async def test_claimed_investigation_remains_readable_after_claim_session_closes():
    """A claimed row is passed to the handler after claim_one's session closes."""

    from agent_server.investigations.worker import InvestigationWorker

    now = datetime.now(timezone.utc)
    row = InvestigationRow(
        id="investigation-1",
        fingerprint="fingerprint",
        status="pending",
        alertname="Alert",
        severity="warning",
        first_seen_at=now,
        last_seen_at=now,
        attempt_count=0,
        max_attempts=3,
        run_after=now,
        created_at=now,
        updated_at=now,
    )

    class Session:
        expunged = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def scalar(self, _query):
            return row

        def add(self, _value):
            pass

        async def flush(self):
            pass

        def expunge(self, value):
            assert value is row
            self.expunged = True

        async def commit(self):
            pass

    session = Session()
    claimed = await InvestigationWorker(lambda: session, worker_id="worker").claim_one()

    assert claimed is row
    assert session.expunged
    assert claimed.id == "investigation-1"
    assert claimed.status == "running"


@pytest.mark.postgres
@pytest.mark.skip(reason="requires disposable PostgreSQL and migration setup")
async def test_two_workers_claim_one_investigation():
    """Real SELECT FOR UPDATE SKIP LOCKED concurrency gate."""
