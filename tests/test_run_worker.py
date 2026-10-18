import pytest

from agent_core import AgentResponse
from agent_server.persistence.memory import InMemoryConversationRepository
from agent_server.run_worker import AgentRunWorker


class FakeRuntime:
    async def run(self, request):
        return AgentResponse(message=f"processed: {request.message}")


@pytest.mark.asyncio
async def test_worker_reclaims_a_run_after_the_previous_worker_lease_expires():
    repository = InMemoryConversationRepository()
    conversation = await repository.create("user-1", "test")
    abandoned, created = await repository.create_or_get_run(
        "user-1", conversation.id, "key-1", "hash-1", "hello"
    )
    assert created

    first_lease = await repository.claim_next_run("old-worker", lease_seconds=0)
    assert first_lease is not None
    assert first_lease.id == abandoned.id
    assert first_lease.attempt == 1

    worker = AgentRunWorker(
        runtime=FakeRuntime(),
        conversations=repository,
        runs=repository,
        worker_id="replacement-worker",
    )
    assert await worker.run_once()

    restored = await repository.get_run("user-1", abandoned.id)
    assert restored is not None
    assert restored.state == "completed"
    assert restored.attempt == 2
    assert restored.message == "processed: hello"
    events = await repository.list_run_events("user-1", abandoned.id)
    assert [event.event_type for event in events] == ["created", "running", "resumed", "completed"]


@pytest.mark.asyncio
async def test_worker_uses_only_history_before_the_message_being_processed():
    repository = InMemoryConversationRepository()
    conversation = await repository.create("user-1", "test")
    await repository.add_message("user-1", conversation.id, "user", "earlier")
    run, _ = await repository.create_or_get_run(
        "user-1", conversation.id, "key-1", "hash-1", "current"
    )
    await repository.add_message("user-1", conversation.id, "user", "future")

    class ObservingRuntime:
        history = None

        async def run(self, request):
            self.history = request.history
            return AgentResponse(message="done")

    runtime = ObservingRuntime()
    worker = AgentRunWorker(runtime=runtime, conversations=repository, runs=repository)
    await worker.run_once()

    assert [item["content"] for item in runtime.history] == ["earlier"]
    assert run.input_message == "current"
