import pytest

from agent_server.investigations.runner import InvestigationRunner


@pytest.mark.asyncio
async def test_runner_can_be_constructed_with_injected_adapters():
    runner = InvestigationRunner(lambda: None)

    assert runner.slack is not None
    assert runner.kube_factory is not None
