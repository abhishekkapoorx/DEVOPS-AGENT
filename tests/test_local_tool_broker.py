import asyncio

import pytest

from agent_core.tools import ToolExecutionContext
from agent_server.local_tool_broker import LocalToolBroker


@pytest.mark.asyncio
async def test_broker_routes_a_tool_call_to_the_user_helper_and_returns_its_result():
    broker = LocalToolBroker(timeout=1)
    assert broker.connect_helper("user-1", "linux", "/workspace")
    context = ToolExecutionContext(
        user_id="user-1",
        run_id="run-1",
        call_id="call-1",
        scopes=frozenset(),
    )

    execution = asyncio.create_task(
        broker.execute(
            name="git.command",
            version="1.0.0",
            arguments={"argv": ["status"], "cwd": None},
            context=context,
        )
    )
    request = await broker.next_call("user-1")

    assert request == {
        "run_id": "run-1",
        "call_id": "call-1",
        "name": "git.command",
        "version": "1.0.0",
        "arguments": {"argv": ["status"], "cwd": None},
    }
    assert broker.submit_result(
        "user-1",
        "call-1",
        {"exit_code": 0, "stdout": "clean", "stderr": "", "duration_ms": 4},
    )

    result = await execution
    assert result.status == "succeeded"
    assert result.output["stdout"] == "clean"


@pytest.mark.asyncio
async def test_broker_rejects_calls_unavailable_on_connected_helper_platform(tmp_path):
    broker = LocalToolBroker(timeout=1)
    assert broker.connect_helper("user-1", "windows", str(tmp_path))
    context = ToolExecutionContext(
        user_id="user-1", run_id="run-1", call_id="call-2", scopes=frozenset()
    )

    result = await broker.execute(
        name="files.grep",
        version="1.0.0",
        arguments={"pattern": "needle"},
        context=context,
    )

    assert result.status == "rejected"
    assert "unavailable on windows" in result.error
