"""Explicit factory registrations for the initial read-only Tool Service slice."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from agent_core.tools import ToolDefinition, ToolExecutionContext
from agent_server.tool_service import ToolRegistry


class GitStatusInput(BaseModel):
    repository_id: str = Field(min_length=1, max_length=128)


class GitStatusOutput(BaseModel):
    repository_id: str
    status: str


class GitStatusTool:
    def __init__(
        self,
        *,
        repositories: dict[str, Path],
        process_factory: Callable = asyncio.create_subprocess_exec,
    ) -> None:
        self.repositories = repositories
        self.process_factory = process_factory

    async def execute(self, arguments: GitStatusInput, context: ToolExecutionContext) -> GitStatusOutput:
        repository = self.repositories.get(arguments.repository_id)
        if repository is None:
            raise ValueError("Unknown repository")
        process = await self.process_factory(
            "git",
            "status",
            "--short",
            "--branch",
            cwd=str(repository),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await process.communicate()
        if process.returncode:
            raise RuntimeError("git status failed")
        return GitStatusOutput(
            repository_id=arguments.repository_id,
            status=stdout[:16_000].decode("utf-8", errors="replace"),
        )


def build_default_registry(
    repositories: dict[str, Path], *, process_factory: Callable = asyncio.create_subprocess_exec
) -> ToolRegistry:
    """Create the initial allow-listed tool registry; adapters are per call."""

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="git.status",
            version="1.0.0",
            description=(
                "Read the current branch and working-tree status of an allowed repository. "
                "Allowed repository_id values: "
                + (", ".join(sorted(repositories)) if repositories else "none configured")
                + "."
            ),
            input_model=GitStatusInput,
            output_model=GitStatusOutput,
            required_scopes=frozenset({"git:read"}),
            risk_class="read_only",
            timeout_seconds=5,
            max_result_bytes=16_384,
        ),
        lambda _context: GitStatusTool(
            repositories=repositories, process_factory=process_factory
        ),
    )
    return registry


__all__ = ["GitStatusInput", "GitStatusOutput", "GitStatusTool", "build_default_registry"]
