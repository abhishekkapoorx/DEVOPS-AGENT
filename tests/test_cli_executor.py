import json

import pytest

from cli.executor import CommandExecutor, ExecutionRequest, ExecutionResult, UnsupportedToolError
from cli.__main__ import main


def test_execution_request_accepts_supported_cli_and_serializes_result():
    request = ExecutionRequest(tool="docker", args=("ps", "-a"))

    assert request.tool == "docker"
    assert request.args == ("ps", "-a")

    result = ExecutionResult(
        tool="docker",
        args=("ps", "-a"),
        exit_code=0,
        stdout="container-id\n",
        stderr="",
        duration_ms=12.5,
    )
    assert json.loads(result.to_json()) == {
        "tool": "docker",
        "args": ["ps", "-a"],
        "exit_code": 0,
        "stdout": "container-id\n",
        "stderr": "",
        "duration_ms": 12.5,
    }


def test_executor_uses_local_environment_and_returns_complete_result():
    calls = []

    def runner(command, *, cwd, env, shell):
        calls.append((command, cwd, env, shell))
        return 7, "output", "warning"

    result = CommandExecutor(runner=runner).execute(
        ExecutionRequest(tool="git", args=("status",), cwd="C:/repo")
    )

    assert result.exit_code == 7
    assert result.stdout == "output"
    assert result.stderr == "warning"
    assert result.duration_ms >= 0
    assert calls == [(("git", "status"), "C:/repo", None, False)]


def test_shell_request_is_executed_as_shell_text():
    calls = []

    def runner(command, *, cwd, env, shell):
        calls.append((command, cwd, env, shell))
        return 0, "ok", ""

    CommandExecutor(runner=runner).execute(
        ExecutionRequest(tool="shell", args=("echo hello",))
    )

    assert calls == [("echo hello", None, None, True)]


def test_unsupported_tools_fail_before_process_execution():
    with pytest.raises(UnsupportedToolError):
        CommandExecutor(runner=lambda *args, **kwargs: pytest.fail("must not run")).execute(
            ExecutionRequest(tool="python", args=("--version",))
        )


def test_cli_one_shot_mode_returns_zero(monkeypatch, capsys):
    class FakeExecutor:
        def execute(self, request):
            return ExecutionResult(request.tool, request.args, 0, "ok", "", 1.0)

    monkeypatch.setattr("cli.__main__.CommandExecutor", FakeExecutor)

    assert main(["--tool", "git", "status"]) == 0
    assert '"exit_code": 0' in capsys.readouterr().out
