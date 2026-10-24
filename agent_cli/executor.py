"""Dependency-free local executor for structured tool requests.

This module intentionally has no dependency on LangGraph or the server agent.
It executes against the user's existing process environment, which lets the
AWS, gcloud, and Kubernetes CLIs resolve local authentication normally.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from agent_protocol import OperationClass, redact_secrets

from .audit import AuditSink, new_record


SUPPORTED_TOOLS = frozenset({"aws", "az", "gcloud", "kubectl", "docker", "git", "files"})
Runner = Callable[..., tuple[int, str, str]]
ApprovalCallback = Callable[["ExecutionRequest", OperationClass], bool]


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
        if not normalized_args:
            raise ValueError("requests must contain an action")
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
    approved: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "args": redact_secrets(list(self.args)),
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_ms": self.duration_ms,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


def _run_subprocess(command: Sequence[str], *, cwd: str | None, env: Mapping[str, str] | None, shell: bool = False) -> tuple[int, str, str]:
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

    def __init__(self, runner: Runner | None = None, *, approval_callback: ApprovalCallback | None = None, audit_sink: AuditSink | None = None, user_id: str = "cli-user", session_id: str = "local", workspace: str | Path | None = None) -> None:
        self._runner = runner or _run_subprocess
        self._approval_callback = approval_callback
        self._audit_sink = audit_sink
        self._user_id = user_id
        self._session_id = session_id
        self.workspace = Path(workspace or Path.cwd()).resolve()
        self.audit_records = []

    @staticmethod
    def _validate_cwd(cwd: str | None) -> str | None:
        if cwd is None:
            return None
        requested = Path(cwd).resolve(strict=False)
        allowed = self.workspace
        try:
            requested.relative_to(allowed)
        except ValueError as exc:
            raise ValueError("working directory is outside the local client workspace") from exc
        if not requested.is_dir():
            raise ValueError("working directory does not exist")
        return os.fspath(requested)

    def execute(self, request: ExecutionRequest | Mapping[str, Any], *, request_id: str = "local") -> ExecutionResult:
        if not isinstance(request, ExecutionRequest):
            request = ExecutionRequest.from_mapping(request)

        action = request.args[0]
        file_change = request.tool == "files" and action in {"write", "delete"}
        operation = OperationClass.WRITE if request.tool != "files" or file_change else OperationClass.READ
        cwd = self._validate_cwd(request.cwd)
        approved = request.tool == "files" and not file_change
        if not approved and self._approval_callback is not None:
            approved = bool(self._approval_callback(request, operation))
        started = time.perf_counter()
        if not approved:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            result = ExecutionResult(request.tool, request.args, 403, "", "Explicit approval required", duration_ms, False)
            self._audit(result, operation.classification, action, started, "denied", request_id)
            return result
        if request.tool == "files":
            try:
                output = self._files(request.args)
                exit_code, stdout, stderr = 0, output[:64_000], ""
            except (OSError, ValueError) as exc:
                exit_code, stdout, stderr = 1, "", str(exc)
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            result = ExecutionResult(request.tool, request.args, exit_code, stdout, stderr, duration_ms)
            self._audit(result, operation, action, started, "succeeded" if exit_code == 0 else "failed", request_id)
            return result
        command: Sequence[str] = (request.tool, *request.args)
        try:
            exit_code, stdout, stderr = self._runner(
                command,
                cwd=cwd,
                env=None,
                shell=False,
            )
        except OSError as exc:
            exit_code, stdout, stderr = 127, "", str(exc)
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        result = ExecutionResult(
            tool=request.tool,
            args=request.args,
            exit_code=exit_code,
            stdout=redact_secrets(stdout[:64_000]),
            stderr=redact_secrets(stderr[:64_000]),
            duration_ms=duration_ms,
        )
        self._audit(result, operation.classification, action, started, "succeeded" if exit_code == 0 else "failed", request_id)
        return result

    def _files(self, args: Sequence[str]) -> str:
        action = args[0]
        if action == "list":
            path = self._file_path(args[1] if len(args) > 1 else ".")
            if not path.is_dir():
                raise ValueError("list requires a directory")
            return "\n".join(sorted(item.name for item in path.iterdir()))
        if action == "read" and len(args) == 2:
            return self._file_path(args[1]).read_text(encoding="utf-8")[:100_000]
        if action == "search" and len(args) >= 2:
            needle = args[1]
            root = self._file_path(args[2] if len(args) > 2 else ".")
            matches = []
            for path in root.rglob("*"):
                try:
                    path.resolve(strict=False).relative_to(self.workspace)
                except ValueError:
                    continue
                if path.is_file() and len(matches) < 500:
                    try:
                        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                            if needle in line:
                                matches.append(f"{path.relative_to(self.workspace)}:{number}:{line[:500]}")
                    except (OSError, UnicodeError):
                        continue
            return "\n".join(matches)
        if action == "write" and len(args) >= 3:
            path = self._file_path(args[1])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(" ".join(args[2:]), encoding="utf-8")
            return f"Wrote {path.relative_to(self.workspace)}"
        if action == "delete" and len(args) == 2:
            path = self._file_path(args[1])
            if path.is_dir():
                raise ValueError("delete only removes files")
            path.unlink()
            return f"Deleted {path.relative_to(self.workspace)}"
        raise ValueError("files supports list [path], read <path>, search <text> [path], write <path> <content>, delete <path>")

    def _file_path(self, value: str) -> Path:
        path = (self.workspace / value).resolve(strict=False)
        try:
            path.relative_to(self.workspace)
        except ValueError as exc:
            raise ValueError("file path is outside the local client workspace") from exc
        return path

    def _audit(self, result: ExecutionResult, operation: OperationClass, action: str, started: float, outcome: str, request_id: str) -> None:
        record = new_record(user_id=self._user_id, session_id=self._session_id, request_id=request_id, tool=result.tool, action=action, operation=operation, outcome=outcome, started_at=started, duration_ms=result.duration_ms, details=result.to_dict())
        self.audit_records.append(record)
        if self._audit_sink is not None:
            self._audit_sink(record)


class LocalExecutionClient:
    """Programmatic client used by local integrations and CLI adapters."""

    def __init__(self, executor: CommandExecutor | None = None) -> None:
        self.executor = executor or CommandExecutor()

    def execute(self, request: ExecutionRequest | Mapping[str, Any]) -> ExecutionResult:
        return self.executor.execute(request)
