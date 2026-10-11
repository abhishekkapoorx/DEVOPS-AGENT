import json
from pathlib import Path

import pytest

from agent_cli.executor import CommandExecutor, ExecutionRequest, ExecutionResult, UnsupportedToolError
from agent_cli.__main__ import main


def test_execution_request_accepts_supported_cli_and_serializes_result():
    request = ExecutionRequest(tool="docker", args=("ps", "-a"))
    assert request.tool == "docker"
    assert request.args == ("ps", "-a")
    result = ExecutionResult("docker", ("ps", "-a"), 0, "container-id\n", "", 12.5)
    assert json.loads(result.to_json()) == {"tool": "docker", "args": ["ps", "-a"], "exit_code": 0, "stdout": "container-id\n", "stderr": "", "duration_ms": 12.5}


def test_executor_uses_argv_and_returns_complete_result():
    calls = []
    def runner(command, *, cwd, env, shell):
        calls.append((command, cwd, env, shell))
        return 7, "output", "warning"
    result = CommandExecutor(runner=runner).execute(ExecutionRequest(tool="git", args=("status",), cwd="."))
    assert result.exit_code == 7
    assert result.stdout == "output"
    assert result.stderr == "warning"
    assert calls == [(('git', 'status'), str(Path.cwd()), None, False)]


def test_shell_requests_are_rejected():
    with pytest.raises(UnsupportedToolError):
        ExecutionRequest(tool="shell", args=("echo hello",))


def test_unsupported_tools_fail_before_process_execution():
    with pytest.raises(UnsupportedToolError):
        CommandExecutor(runner=lambda *args, **kwargs: pytest.fail("must not run")).execute(ExecutionRequest(tool="python", args=("--version",)))


def test_destructive_operations_require_explicit_approval():
    calls = []
    runner = lambda *args, **kwargs: calls.append((args, kwargs)) or (0, "", "")
    denied = CommandExecutor(runner=runner).execute(ExecutionRequest(tool="git", args=("reset", "--hard")))
    assert denied.exit_code == 403
    assert denied.approved is False
    assert calls == []
    approved = CommandExecutor(runner=runner, approval_callback=lambda request, operation: True).execute(ExecutionRequest(tool="git", args=("reset", "--hard")))
    assert approved.exit_code == 0
    assert calls[0][0][0] == ("git", "reset", "--hard")
    assert calls[0][1]["shell"] is False


def test_unknown_actions_fail_closed():
    with pytest.raises(ValueError, match="Unknown or unauthorized"):
        CommandExecutor(runner=lambda *args, **kwargs: pytest.fail("must not run")).execute(ExecutionRequest(tool="git", args=("run_arbitrary",)))


def test_command_output_is_redacted():
    result = CommandExecutor(runner=lambda *args, **kwargs: (0, "TOKEN=secret-value", "Bearer abc")).execute(ExecutionRequest(tool="git", args=("status",)))
    assert "secret-value" not in result.stdout
    assert "abc" not in result.stderr


def test_cli_one_shot_mode_returns_zero(monkeypatch, capsys):
    class FakeExecutor:
        def execute(self, request):
            return ExecutionResult(request.tool, request.args, 0, "ok", "", 1.0)
    monkeypatch.setattr("agent_cli.__main__.CommandExecutor", FakeExecutor)
    assert main(["--tool", "git", "status"]) == 0
    assert '"exit_code": 0' in capsys.readouterr().out
