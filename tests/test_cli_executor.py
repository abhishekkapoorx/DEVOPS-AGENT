import json

import pytest

from agent_cli.__main__ import main
from agent_cli.executor import ExecutionResult, LocalToolExecutor


def test_command_execution_uses_argv_without_a_shell(tmp_path):
    calls = []

    def runner(command, *, cwd, env, shell):
        calls.append((command, cwd, env, shell))
        return 7, "output", "warning"

    result = LocalToolExecutor(
        runner=runner,
        approval_callback=lambda *_: True,
        workspace=tmp_path,
    ).execute("git.command", {"argv": ["status"], "cwd": None})

    assert result.exit_code == 7
    assert result.stdout == "output"
    assert result.stderr == "warning"
    assert calls == [(('git', 'status'), str(tmp_path), None, False)]


def test_commands_require_approval_and_are_not_run_when_denied(tmp_path):
    calls = []
    executor = LocalToolExecutor(
        runner=lambda *args, **kwargs: calls.append((args, kwargs)) or (0, "", ""),
        workspace=tmp_path,
    )

    result = executor.execute("git.command", {"argv": ["status"], "cwd": None})

    assert result.exit_code == 403
    assert result.approved is False
    assert calls == []


def test_command_runs_after_explicit_approval(tmp_path):
    calls = []
    executor = LocalToolExecutor(
        runner=lambda command, **kwargs: calls.append((command, kwargs)) or (0, "clean", ""),
        approval_callback=lambda _name, _arguments, _operation: True,
        workspace=tmp_path,
    )

    result = executor.execute("git.command", {"argv": ["status"], "cwd": None})

    assert result.exit_code == 0
    assert result.approved is True
    assert calls[0][0] == ("git", "status")
    assert calls[0][1]["shell"] is False


def test_unsupported_or_invalid_tool_calls_fail_before_execution(tmp_path):
    executor = LocalToolExecutor(
        runner=lambda *args, **kwargs: pytest.fail("must not run"), workspace=tmp_path
    )

    unsupported = executor.execute("python.command", {"argv": ["--version"], "cwd": None})
    malformed = executor.execute("git.command", {"argv": "status", "cwd": None})

    assert unsupported.exit_code == 2
    assert malformed.exit_code == 2


def test_command_working_directory_cannot_escape_workspace(tmp_path):
    executor = LocalToolExecutor(
        runner=lambda *args, **kwargs: pytest.fail("must not run"),
        approval_callback=lambda *_: True,
        workspace=tmp_path,
    )

    result = executor.execute(
        "git.command", {"argv": ["status"], "cwd": "../outside"}
    )

    assert result.exit_code == 2
    assert "outside the local client workspace" in result.stderr


def test_result_redacts_secrets_and_bounds_output():
    result = LocalToolExecutor(
        runner=lambda *args, **kwargs: (0, "TOKEN=secret-value" + "x" * 70_000, "Bearer abc"),
        approval_callback=lambda *_: True,
    ).execute("git.command", {"argv": ["status"], "cwd": None})

    serialized = json.loads(result.to_json())
    assert "secret-value" not in serialized["stdout"]
    assert "abc" not in serialized["stderr"]
    assert len(serialized["stdout"]) <= 64_000


def test_cli_one_shot_mode_uses_named_local_tool_arguments(monkeypatch, capsys):
    calls = []

    class FakeExecutor:
        def __init__(self, **_kwargs):
            pass

        def execute(self, name, arguments):
            calls.append((name, arguments))
            return ExecutionResult(name, arguments, 0, "ok", "", 1.0)

    monkeypatch.setattr("agent_cli.__main__.LocalToolExecutor", FakeExecutor)

    assert main(["--tool", "git", "status"]) == 0
    assert calls == [("git.command", {"argv": ["status"]})]
    assert json.loads(capsys.readouterr().out)["exit_code"] == 0


def test_cli_rest_mode_streams_progress_before_final_result(monkeypatch, capsys):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def ask(self, message, *, conversation_id=None, on_event=None):
            on_event({"type": "agent_message", "message": "Checking", "final": False})
            return {"message": "Done"}

    class FakeTokens:
        access_token = "short-lived-access"
        user_id = "verified-user"

    class FakeAuth:
        def __init__(self, **kwargs):
            pass

        def restore(self):
            return FakeTokens()

    monkeypatch.setattr("agent_cli.rest_client.RestAgentClient", FakeClient)
    monkeypatch.setattr("agent_cli.auth.DeviceLogin", FakeAuth)
    assert main(["--api-url", "https://agent.example", "--ask", "Check"]) == 0
    captured = capsys.readouterr()
    assert "Checking" in captured.err
    assert captured.out.strip() == "Done"


def test_cli_does_not_accept_access_tokens_as_arguments():
    with pytest.raises(SystemExit):
        main(["--api-url", "https://agent.example", "--token", "secret", "--ask", "Check"])
