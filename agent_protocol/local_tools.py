"""Shared contract for tool requests executed by the user's local helper."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from .security import OperationClass


PLATFORMS = frozenset({"linux", "windows", "other"})
COMMAND_TOOL_NAMES = ("aws", "az", "gcloud", "kubectl", "docker", "git")


class _Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CommandArguments(_Arguments):
    argv: list[StrictStr] = Field(min_length=1, max_length=256)
    cwd: StrictStr | None = Field(default=None, max_length=4_096)


class ListFilesArguments(_Arguments):
    path: StrictStr = Field(min_length=1, max_length=4_096)


class SearchArguments(_Arguments):
    pattern: StrictStr = Field(min_length=1, max_length=16_384)


@dataclass(frozen=True)
class LocalToolDefinition:
    name: str
    version: str
    arguments: type[BaseModel]
    platforms: frozenset[str]
    operation: OperationClass

    @property
    def tool(self) -> str:
        return self.name.partition(".")[0]

    @property
    def action(self) -> str:
        return self.name.partition(".")[2]

    def available_on(self, platform: str) -> bool:
        return platform in self.platforms

    def as_tool_definition(self, description: str) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": description,
            "input_schema": self.arguments.model_json_schema(),
            "required_scopes": [],
            "risk_class": "read_only" if self.operation == OperationClass.READ else "write",
        }


_ALL_PLATFORMS = PLATFORMS
LOCAL_TOOL_DEFINITIONS = tuple(
    LocalToolDefinition(
        name=f"{tool}.command",
        version="1.0.0",
        arguments=CommandArguments,
        platforms=_ALL_PLATFORMS,
        operation=OperationClass.WRITE,
    )
    for tool in COMMAND_TOOL_NAMES
) + (
    LocalToolDefinition(
        "files.list_files", "1.0.0", ListFilesArguments, _ALL_PLATFORMS,
        OperationClass.READ,
    ),
    LocalToolDefinition(
        "files.grep", "1.0.0", SearchArguments, frozenset({"linux"}),
        OperationClass.READ,
    ),
    LocalToolDefinition(
        "files.ripgrep", "1.0.0", SearchArguments, frozenset({"windows"}),
        OperationClass.READ,
    ),
)
_DEFINITIONS_BY_NAME = {definition.name: definition for definition in LOCAL_TOOL_DEFINITIONS}


def local_tool_definition(name: str, version: str = "1.0.0") -> LocalToolDefinition | None:
    definition = _DEFINITIONS_BY_NAME.get(name)
    return definition if definition is not None and definition.version == version else None


def available_local_tool_definitions(platform: str) -> tuple[LocalToolDefinition, ...]:
    return tuple(
        definition for definition in LOCAL_TOOL_DEFINITIONS
        if definition.available_on(platform)
    )


def validate_local_tool_arguments(
    name: str,
    arguments: dict[str, Any],
    *,
    platform: str,
    version: str = "1.0.0",
) -> tuple[LocalToolDefinition, dict[str, Any]]:
    definition = local_tool_definition(name, version)
    if definition is None:
        raise ValueError(f"Unsupported local tool: {name}")
    if not definition.available_on(platform):
        raise ValueError(f"Local tool {name} is unavailable on {platform}")
    parsed = definition.arguments.model_validate(arguments)
    normalized = parsed.model_dump()
    if name.endswith(".command"):
        size = sum(len(value.encode("utf-8")) for value in normalized["argv"])
        if size > 64_000:
            raise ValueError("Tool arguments exceed the size limit")
    else:
        value = next(iter(normalized.values()))
        if len(value.encode("utf-8")) > 16_384:
            raise ValueError("Tool argument exceeds the size limit")
    return definition, normalized


__all__ = [
    "COMMAND_TOOL_NAMES", "CommandArguments", "LOCAL_TOOL_DEFINITIONS",
    "ListFilesArguments", "LocalToolDefinition", "PLATFORMS", "SearchArguments",
    "available_local_tool_definitions", "local_tool_definition",
    "validate_local_tool_arguments",
]
