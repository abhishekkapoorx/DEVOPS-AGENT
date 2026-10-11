"""Dependency-free local executor for structured tool requests.

This module intentionally has no dependency on LangGraph or the server agent.
It executes against the user's existing process environment, which lets the
AWS, gcloud, and Kubernetes CLIs resolve local authentication normally.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence


SUPPORTED_TOOLS = frozenset({"aws", "gcloud", "kubectl", "docker", "git", "shell"})
Runner = Callable[..., tuple[int, str, str]]


class UnsupportedToolError(ValueError):
    """Raised when a request names a tool outside the local client contract."""


@dataclass(frozen=True)
class ExecutionRequest:
    """A serializable request for one local CLI operation."""

    tool: str
    args: tuple[str, ...]
    cwd: str | None = None

    def __post_init__(self) -> None:
        if self.tool not in SUPPORTED_TOOLS:
            raise UnsupportedToolError(
                f"Unsupported tool {self.tool!r}; choose one of {sorted(SUPPORTED_TOOLS)}"
            )
        normalized_args = tuple(str(arg) for arg in self.args)
        if self.tool == "shell" and len(normalized_args) != 1:
            raise ValueError("shell requests must contain exactly one command string")
        object.__setattr__(self, "args", normalized_args)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExecutionRequest":
        args = value.get("args", ())
        if isinstance(args, str):
            args = (args,)
        return cls(tool=str(value["tool"]), args=tuple(args), cwd=value.get("cwd"))


@dataclass(frozen=True)
class ExecutionResult:
    """Complete, transport-friendly result of one execution."""

    tool: str
    args: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "args": list(self.args),
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


def _run_subprocess(command: Sequence[str] | str, *, cwd: str | None, env: Mapping[str, str] | None, shell: bool) -> tuple[int, str, str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        shell=shell,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


class CommandExecutor:
    """Execute supported local tools through one common contract."""

    def __init__(self, runner: Runner | None = None) -> None:
        self._runner = runner or _run_subprocess

    def execute(self, request: ExecutionRequest | Mapping[str, Any]) -> ExecutionResult:
        if not isinstance(request, ExecutionRequest):
            request = ExecutionRequest.from_mapping(request)

        shell = request.tool == "shell"
        command: Sequence[str] | str = request.args[0] if shell else (request.tool, *request.args)
        started = time.perf_counter()
        try:
            exit_code, stdout, stderr = self._runner(
                command,
                cwd=request.cwd,
                env=None,  # Preserve local authentication and environment variables.
                shell=shell,
            )
        except OSError as exc:
            exit_code, stdout, stderr = 127, "", str(exc)
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        return ExecutionResult(
            tool=request.tool,
            args=request.args,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
        )


class LocalExecutionClient:
    """Programmatic client used by local integrations and CLI adapters."""

    def __init__(self, executor: CommandExecutor | None = None) -> None:
        self.executor = executor or CommandExecutor()

    def execute(self, request: ExecutionRequest | Mapping[str, Any]) -> ExecutionResult:
        return self.executor.execute(request)
