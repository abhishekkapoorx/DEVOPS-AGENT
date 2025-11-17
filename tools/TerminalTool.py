"""
Terminal tools that respect the agent runtime context.
"""

from __future__ import annotations

import subprocess
from typing import Optional

from langchain_core.tools import tool
from loguru import logger

from utils.context import get_current_context, get_working_directory

_BLOCKED_COMMAND_MESSAGES = {
    "ls_recursive": (
        "The command `ls -R` (recursive list) generates extremely large outputs and "
        "is disabled to avoid rate limits. Please explore the filesystem gradually, "
        "e.g., run `ls <directory>` for specific folders or use targeted commands such "
        "as `find <path> -maxdepth 2 -type d`."
    )
}

_MAX_OUTPUT_CHARS = 20000


def _is_recursive_ls(command: str) -> bool:
    """Return True if the command attempts a recursive ls."""
    stripped = command.strip()
    if not stripped.lower().startswith("ls"):
        return False

    # Quick check for -R/--recursive flags
    tokens = stripped.split()
    for token in tokens[1:]:
        if token in {"-R", "--recursive"}:
            return True
        if token.startswith("-") and "R" in token:
            return True
    return False


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
    """Execute a Windows command in the agent's working directory.
    
    This tool respects the runtime context's working_directory setting,
    ensuring commands execute in the correct project directory.
    """
    context = get_current_context()
    working_dir = get_working_directory(context)
    
    logger.debug(f"Executing Windows command in working directory: {working_dir}")
    logger.debug(f"Command: {command}")

    try:
        result = _subprocess_run(command, cwd=working_dir)
        output = result.stdout if result.stdout else result.stderr
        if len(output) > _MAX_OUTPUT_CHARS:
            logger.warning(
                f"Command output truncated from {len(output)} to {_MAX_OUTPUT_CHARS} characters"
            )
            return (
                output[:_MAX_OUTPUT_CHARS]
                + "\n\n[output truncated — use narrower commands or filters]"
            )
        return output
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Error executing command '{command}': {exc}")
        return f"Error: {exc}"


@tool
def shell_tool(command: str) -> str:
    """Execute a POSIX shell command safely within the agent's working directory.
    
    This tool respects the runtime context's working_directory setting,
    ensuring commands execute in the correct project directory.
    
    Note: Recursive `ls -R` commands are blocked to prevent rate limit issues
    from excessive output. Use targeted directory exploration instead.
    """
    context = get_current_context()
    working_dir = get_working_directory(context)
    
    logger.debug(f"Executing shell command in working directory: {working_dir}")
    logger.debug(f"Command: {command}")

    if _is_recursive_ls(command):
        logger.warning(f"Blocked recursive ls command: {command}")
        return _BLOCKED_COMMAND_MESSAGES["ls_recursive"]

    try:
        result = _subprocess_run(command, cwd=working_dir)
        output = result.stdout if result.stdout else result.stderr
        if len(output) > _MAX_OUTPUT_CHARS:
            logger.warning(
                f"Command output truncated from {len(output)} to {_MAX_OUTPUT_CHARS} characters"
            )
            return (
                output[:_MAX_OUTPUT_CHARS]
                + "\n\n[output truncated — refine the command to limit output volume]"
            )
        return output
    except Exception as exc:  # pragma: no cover - defensive
        logger.error(f"Error executing command '{command}': {exc}")
        return f"Error: {exc}"