"""
Terminal tools that respect the agent runtime context.
"""

from __future__ import annotations

import subprocess
from typing import Optional

from langchain_core.tools import tool
from langchain_community.tools.shell.tool import ShellTool

from utils.context import get_current_context, get_working_directory

shell_tool = ShellTool()


def _subprocess_run(command: str, *, cwd: Optional[str] = None) -> subprocess.CompletedProcess[str]:
    """Helper to execute subprocess with context-aware working directory."""
    return subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        cwd=cwd,
    )


@tool
def run_windows_command(command: str) -> str:
    """Execute a Windows command in the agent's working directory."""
    context = get_current_context()
    working_dir = get_working_directory(context)

    try:
        result = _subprocess_run(command, cwd=working_dir)
        return result.stdout if result.stdout else result.stderr
    except Exception as exc:  # pragma: no cover - defensive
        return f"Error: {exc}"