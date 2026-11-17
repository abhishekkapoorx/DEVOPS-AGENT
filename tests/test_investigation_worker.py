import pytest

from agent_server.investigations.worker import backoff_seconds


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


@pytest.mark.postgres
@pytest.mark.skip(reason="requires disposable PostgreSQL and migration setup")
async def test_two_workers_claim_one_investigation():
    """Real SELECT FOR UPDATE SKIP LOCKED concurrency gate."""
