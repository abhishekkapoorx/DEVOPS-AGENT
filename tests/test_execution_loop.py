import pytest

from agent_loop import ExecutionLoop, LoopResponse
from cli import ExecutionResult
from server_agent import AgentResponse, SessionContext, ToolRequest


class FakeAgent:
    def __init__(self):
        self.calls = []

    async def arun(self, *, user_id, session_id, message, history=None):
        self.calls.append((user_id, session_id, message, tuple(history or ())))
        if len(self.calls) == 1:
            return AgentResponse(
                context=SessionContext(user_id=user_id, session_id=session_id),
                message="I need the container list.",
                requests=(ToolRequest(tool="docker", action="ps", arguments={}),),
            )
        return AgentResponse(
            context=SessionContext(user_id=user_id, session_id=session_id),
            message="The container list is empty.",
            requests=(),
        )


class FakeExecutor:
    def __init__(self):
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return ExecutionResult(
            tool=request.tool,
            args=request.args,
            exit_code=0,
            stdout="CONTAINER LIST\n",
            stderr="",
            duration_ms=1.0,
        )


@pytest.mark.asyncio
async def test_loop_executes_requests_and_feeds_results_to_next_agent_turn():
    agent = FakeAgent()
    executor = FakeExecutor()

    response = await ExecutionLoop(agent=agent, executor=executor).run(
        user_id="u-1", session_id="s-1", message="List my containers"
    )

    assert isinstance(response, LoopResponse)
    assert response.message == "The container list is empty."
    assert executor.requests[0].tool == "docker"
    assert executor.requests[0].args == ("ps",)
    assert "CONTAINER LIST" in agent.calls[1][2]
    assert len(agent.calls[1][3]) >= 2


@pytest.mark.asyncio
async def test_loop_preserves_nonzero_results_without_losing_session():
    class FailingExecutor(FakeExecutor):
        def execute(self, request):
            self.requests.append(request)
            return ExecutionResult(request.tool, request.args, 2, "", "permission denied", 1.0)

    agent = FakeAgent()
    response = await ExecutionLoop(agent=agent, executor=FailingExecutor()).run(
        user_id="u-1", session_id="s-1", message="List my containers"
    )

    assert response.executions[0].result.exit_code == 2
    assert "permission denied" in agent.calls[1][2]


@pytest.mark.asyncio
async def test_loop_calls_policy_before_execution():
    decisions = []

    def policy(request, *, user_id, session_id):
        decisions.append((request.tool, user_id, session_id))
        return False

    executor = FakeExecutor()
    response = await ExecutionLoop(
        agent=FakeAgent(), executor=executor, policy=policy
    ).run(user_id="u-1", session_id="s-1", message="List my containers")

    assert decisions == [("docker", "u-1", "s-1")]
    assert executor.requests == []
    assert response.executions[0].result.exit_code == 403
    assert "approval" in response.executions[0].result.stderr.lower()


@pytest.mark.asyncio
async def test_loop_reuses_state_for_the_same_session():
    agent = FakeAgent()
    loop = ExecutionLoop(agent=agent, executor=FakeExecutor())

    await loop.run(user_id="u-1", session_id="s-1", message="List my containers")
    await loop.run(user_id="u-1", session_id="s-1", message="Summarize that")

    assert len(agent.calls[2][3]) >= 4
