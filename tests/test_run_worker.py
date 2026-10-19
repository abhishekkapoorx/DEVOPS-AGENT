import asyncio
import pytest

from agent_core import AgentResponse, AgentToolCall
from agent_core.tools import ToolResult
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


@pytest.mark.asyncio
async def test_worker_executes_registered_tool_and_returns_result_to_runtime():
    repository = InMemoryConversationRepository()
    conversation = await repository.create("user-1", "test")
    run, _ = await repository.create_or_get_run(
        "user-1", conversation.id, "key-1", "hash-1", "check git"
    )

    class Runtime:
        requests = []

        async def run(self, request):
            self.requests.append(request)
            if not request.tool_results:
                return AgentResponse(
                    message="",
                    tool_calls=(
                        AgentToolCall(
                            call_id="call-1",
                            name="git.status",
                            version="1.0.0",
                            arguments={"repository_id": "repo-1"},
                        ),
                    ),
                )
            assert request.tool_results[0]["output"] == {"status": "clean"}
            return AgentResponse(message="The working tree is clean.")

    class Tools:
        contexts = []

        async def list_tools(self, *, context):
            assert context.user_id == "user-1"
            assert context.scopes == frozenset({"git:read"})
            return (
                {
                    "name": "git.status",
                    "version": "1.0.0",
                    "description": "Read git status.",
                    "input_schema": {"type": "object"},
                },
            )

        async def execute(self, *, name, version, arguments, context):
            self.contexts.append(context)
            assert name == "git.status"
            assert version == "1.0.0"
            assert arguments["repository_id"] == "repo-1"
            return ToolResult(
                call_id=context.call_id,
                name=name,
                status="succeeded",
                output={"status": "clean"},
            )

    runtime, tools = Runtime(), Tools()
    worker = AgentRunWorker(
        runtime=runtime,
        conversations=repository,
        runs=repository,
        tool_executor=tools,
        tool_scopes_for_user=lambda user_id: frozenset({"git:read"}) if user_id == "user-1" else frozenset(),
    )
    await worker.run_once()

    restored = await repository.get_run("user-1", run.id)
    assert restored is not None and restored.state == "completed"
    assert restored.message == "The working tree is clean."
    assert restored.tool_calls[0]["result"]["status"] == "succeeded"
    assert len(runtime.requests) == 2
    assert runtime.requests[0].available_tools[0]["name"] == "git.status"
    assert tools.contexts[0].idempotency_key == f"{run.id}:call-1"
    assert tools.contexts[0].scopes == frozenset({"git:read"})


@pytest.mark.asyncio
async def test_cancelling_a_run_is_owner_scoped_and_replayed_as_an_event():
    repository = InMemoryConversationRepository()
    conversation = await repository.create("user-1", "test")
    run, _ = await repository.create_or_get_run(
        "user-1",
        conversation.id,
        "key-1",
        "hash-1",
        "hello",
        correlation_id="corr-1",
        traceparent="00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01",
    )

    assert await repository.cancel_run("other-user", run.id) is None
    cancelled = await repository.cancel_run("user-1", run.id)
    assert cancelled is not None and cancelled.state == "cancelled"
    assert cancelled.correlation_id == "corr-1"
    assert cancelled.traceparent == "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01"
    events = await repository.list_run_events("user-1", run.id)
    assert events[-1].event_type == "cancelled"


@pytest.mark.asyncio
async def test_worker_cancellation_stops_the_active_runtime_task():
    repository = InMemoryConversationRepository()
    conversation = await repository.create("user-1", "test")
    run, _ = await repository.create_or_get_run(
        "user-1", conversation.id, "key-1", "hash-1", "long task"
    )

    class BlockingRuntime:
        started = asyncio.Event()

        async def run(self, request):
            self.started.set()
            await asyncio.Event().wait()

    runtime = BlockingRuntime()
    worker = AgentRunWorker(runtime=runtime, conversations=repository, runs=repository)
    task = asyncio.create_task(worker.run_once())
    await runtime.started.wait()
    await repository.cancel_run("user-1", run.id)

    assert worker.cancel(run.id)
    with pytest.raises(asyncio.CancelledError):
        await task
    cancelled = await repository.get_run("user-1", run.id)
    assert cancelled is not None and cancelled.state == "cancelled"


@pytest.mark.asyncio
async def test_worker_logs_sanitized_runtime_failure_but_persists_generic_error(caplog):
    repository = InMemoryConversationRepository()
    conversation = await repository.create("user-1", "test")
    run, _ = await repository.create_or_get_run(
        "user-1", conversation.id, "key-1", "hash-1", "hello"
    )

    class FailingRuntime:
        async def run(self, request):
            raise RuntimeError("provider rejected api_key=example-secret")

    worker = AgentRunWorker(
        runtime=FailingRuntime(), conversations=repository, runs=repository
    )
    await worker.run_once()

    restored = await repository.get_run("user-1", run.id)
    assert restored is not None and restored.state == "failed"
    assert restored.error == "Agent runtime failed"
    assert "RuntimeError" in caplog.text
    assert "[REDACTED]" in caplog.text
    assert "example-secret" not in caplog.text
