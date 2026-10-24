"""Command-line tool implementation shared by the supported CLIs."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


Runner = Callable[..., tuple[int, str, str]]


def run_command(
    tool: str,
    arguments: Mapping[str, Any],
    *,
    workspace: Path,
    runner: Runner | None = None,
) -> tuple[int, str, str]:
    argv = arguments["argv"]
    cwd = arguments.get("cwd")
    command = (tool, *argv)
    run = runner or _run_subprocess
    try:
        return run(command, cwd=str(cwd or workspace), env=None, shell=False)
    except OSError as exc:
        return 127, "", str(exc)


def _run_subprocess(
    command: Sequence[str], *, cwd: str | None, env: Mapping[str, str] | None,
    shell: bool = False,
) -> tuple[int, str, str]:
    completed = subprocess.run(
        command, cwd=cwd, env=env, shell=shell,
        capture_output=True, text=True, check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr
