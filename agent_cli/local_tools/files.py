"""File and search tools scoped to the CLI launch directory."""

from __future__ import annotations

import os
import platform as host_platform
from pathlib import Path
from typing import Sequence

from .commands import Runner, _run_subprocess


def list_files(path: str, *, workspace: Path) -> tuple[int, str, str]:
    requested = Path(path)
    if not requested.is_absolute():
        raise ValueError("list_files requires an absolute directory path")
    target = _inside_workspace(requested, workspace)
    if not target.is_dir():
        raise ValueError("list_files requires a directory")
    return 0, "\n".join(sorted(item.name for item in target.iterdir())), ""


def search(
    tool: str,
    pattern: str,
    *,
    workspace: Path,
    runner: Runner | None = None,
) -> tuple[int, str, str]:
    system = host_platform.system().lower()
    if tool == "grep":
        if system != "linux":
            raise ValueError("grep is available only on Linux")
        command: Sequence[str] = ("grep", "-r", "-n", "--", pattern, os.fspath(workspace))
    elif tool == "ripgrep":
        if system != "windows":
            raise ValueError("ripgrep is available only on Windows")
        command = (
            os.fspath(_bundled_ripgrep()), "--no-config", "--line-number",
            "--no-heading", "--color", "never", "--", pattern,
            os.fspath(workspace),
        )
    else:
        raise ValueError(f"Unsupported search tool: {tool}")
    try:
        code, stdout, stderr = (runner or _run_subprocess)(
            command, cwd=os.fspath(workspace), env=None, shell=False
        )
    except OSError as exc:
        raise ValueError(f"Could not start {tool}: {exc}") from exc
    if code == 1:
        return 0, "", ""
    if code != 0:
        return code, "", stderr[:4_000] or f"{tool} failed with exit code {code}"
    return 0, stdout[:64_000], ""


def _inside_workspace(path: Path, workspace: Path) -> Path:
    target = path.resolve(strict=False)
    try:
        target.relative_to(workspace)
    except ValueError as exc:
        raise ValueError("file path is outside the local client workspace") from exc
    return target


def _bundled_ripgrep() -> Path:
    machine = host_platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        architecture = "windows_arm64"
    elif machine in {"amd64", "x86_64", "x64"}:
        architecture = "windows_x64"
    else:
        raise ValueError(f"Bundled ripgrep does not support Windows architecture {machine!r}")
    executable = Path(__file__).parents[1] / "bin" / architecture / "rg.exe"
    if not executable.is_file():
        raise ValueError(f"Bundled ripgrep is unavailable for Windows architecture {machine!r}")
    return executable
