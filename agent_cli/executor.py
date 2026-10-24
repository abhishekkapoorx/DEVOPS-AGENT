"""Common dispatcher for tools that run on the user's machine."""

from __future__ import annotations

import json
import os
import platform as host_platform
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from agent_protocol import (
    COMMAND_TOOL_NAMES,
    OperationClass,
    redact_secrets,
    validate_local_tool_arguments,
)

from .audit import AuditSink, new_record
from .local_tools import commands, files


COMMAND_TOOLS = frozenset(COMMAND_TOOL_NAMES)
SUPPORTED_TOOLS = COMMAND_TOOLS | {"files"}
Runner = Callable[..., tuple[int, str, str]]
ApprovalCallback = Callable[[str, Mapping[str, Any], OperationClass], bool]


class UnsupportedToolError(ValueError):
    """Raised when a request names a tool that the local client cannot run."""


@dataclass(frozen=True)
class ExecutionResult:
    """Result shared by the CLI display and helper transport."""

    name: str
    arguments: Mapping[str, Any]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    approved: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "arguments": redact_secrets(dict(self.arguments)),
            "exit_code": self.exit_code,
            "stdout": _redact_bounded(self.stdout),
            "stderr": _redact_bounded(self.stderr),
            "duration_ms": self.duration_ms,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


class LocalToolExecutor:
    """Apply shared safety rules, then dispatch to a tool-specific function."""

    def __init__(
        self,
        runner: Runner | None = None,
        *,
        approval_callback: ApprovalCallback | None = None,
        audit_sink: AuditSink | None = None,
        user_id: str = "cli-user",
        session_id: str = "local",
        workspace: str | Path | None = None,
    ) -> None:
        self._runner = runner
        self._approval_callback = approval_callback
        self._audit_sink = audit_sink
        self._user_id = user_id
        self._session_id = session_id
        self.workspace = Path(workspace or Path.cwd()).resolve()
        self.audit_records = []

    def execute(
        self,
        name: str,
        arguments: Mapping[str, Any],
        *,
        request_id: str = "local",
    ) -> ExecutionResult:
        started = time.perf_counter()
        tool_name = name if isinstance(name, str) else "<invalid>"
        normalized = dict(arguments) if isinstance(arguments, Mapping) else {}
        definition = None
        try:
            if not isinstance(name, str) or not isinstance(arguments, Mapping):
                raise ValueError("tool name and argument object are required")
            definition, normalized = validate_local_tool_arguments(
                name, normalized, platform=_client_platform()
            )
            handler, action = self._handler(name, normalized)
        except (TypeError, ValueError, KeyError) as exc:
            result = self._result(tool_name, normalized, 2, "", str(exc), started, False)
            self._audit(
                result,
                definition.operation if definition else None,
                definition.action if definition else "validation",
                started,
                "rejected",
                request_id,
            )
            return result

        operation = definition.operation
        approved = operation == OperationClass.READ
        if not approved and self._approval_callback is not None:
            approved = bool(self._approval_callback(name, normalized, operation))
        if not approved:
            result = self._result(name, normalized, 403, "", "Explicit approval required", started, False)
            self._audit(result, operation, action, started, "denied", request_id)
            return result
        try:
            exit_code, stdout, stderr = handler(normalized)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            exit_code, stdout, stderr = 1, "", str(exc)
        result = self._result(name, normalized, exit_code, stdout, stderr, started)
        self._audit(result, operation, action, started, "succeeded" if exit_code == 0 else "failed", request_id)
        return result

    def _handler(self, name: str, arguments: dict[str, Any]):
        if name in {f"{tool}.command" for tool in COMMAND_TOOLS}:
            tool = name.partition(".")[0]
            _validate_command_cwd(arguments, self.workspace)
            return (
                lambda args: commands.run_command(
                    tool, args, workspace=self.workspace, runner=self._runner
                ),
                "command",
            )
        if name == "files.list_files":
            return (
                lambda args: files.list_files(args["path"], workspace=self.workspace),
                "list_files",
            )
        if name in {"files.grep", "files.ripgrep"}:
            return (
                lambda args: files.search(
                    name.partition(".")[2], args["pattern"], workspace=self.workspace,
                    runner=self._runner,
                ),
                name.partition(".")[2],
            )
        raise UnsupportedToolError(f"Unknown or unauthorized local tool: {name}")

    def _result(
        self, name: str, arguments: Mapping[str, Any], exit_code: int,
        stdout: str, stderr: str, started: float, approved: bool = True,
    ) -> ExecutionResult:
        return ExecutionResult(
            name=name,
            arguments=arguments,
            exit_code=exit_code,
            stdout=redact_secrets(stdout[:64_000]),
            stderr=redact_secrets(stderr[:64_000]),
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            approved=approved,
        )

    def _audit(self, result, operation, action, started, outcome, request_id) -> None:
        record = new_record(
            user_id=self._user_id,
            session_id=self._session_id,
            request_id=request_id,
            tool=result.name,
            action=action,
            operation=operation,
            outcome=outcome,
            started_at=started,
            duration_ms=result.duration_ms,
            details=result.to_dict(),
        )
        self.audit_records.append(record)
        if self._audit_sink is not None:
            self._audit_sink(record)


def _redact_bounded(value: str) -> str:
    """Keep the wire result within the server limit after redaction expands text."""
    return redact_secrets(value)[:64_000]


def _validate_command_cwd(arguments: dict[str, Any], workspace: Path) -> None:
    cwd = arguments.get("cwd")
    if cwd is not None:
        path = (workspace / cwd).resolve(strict=False)
        try:
            path.relative_to(workspace)
        except ValueError as exc:
            raise ValueError("working directory is outside the local client workspace") from exc
        if not path.is_dir():
            raise ValueError("working directory does not exist")
        arguments["cwd"] = os.fspath(path)


def _client_platform() -> str:
    system = host_platform.system().lower()
    if system == "linux":
        return "linux"
    if system == "windows":
        return "windows"
    return "other"
