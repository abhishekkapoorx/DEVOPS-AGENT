"""Dependency-light security policy primitives shared by the client and server."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class OperationClass(StrEnum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"


class UnknownOperationError(ValueError):
    """Raised when a tool/action pair is not in the explicit policy."""


@dataclass(frozen=True)
class OperationPolicy:
    tool: str
    action: str
    classification: OperationClass


# A closed catalog is intentional. New operations must be reviewed and added here.
_POLICIES: dict[tuple[str, str], OperationClass] = {
    ("aws", action): OperationClass.READ for action in {"get", "list", "describe", "status", "logs", "whoami", "get_caller_identity"}
}
_POLICIES.update({("aws", action): OperationClass.WRITE for action in {"provision", "create", "update", "apply"}})
_POLICIES.update({("aws", action): OperationClass.DESTRUCTIVE for action in {"delete", "destroy", "terminate"}})
for tool in ("az", "gcloud", "kubectl", "docker", "git", "files"):
    _POLICIES.update({(tool, action): OperationClass.READ for action in {"status", "get", "list", "describe", "inspect", "diff", "log", "logs", "show", "search", "images", "ps"}})
_POLICIES.update({(tool, action): OperationClass.WRITE for tool in ("az", "gcloud", "kubectl", "docker", "git", "files") for action in {"provision", "create", "update", "apply", "build", "pull", "run", "start", "write", "add", "commit", "checkout", "copy", "move"}})
_POLICIES.update({(tool, action): OperationClass.DESTRUCTIVE for tool in ("az", "gcloud", "kubectl", "docker", "git", "files") for action in {"delete", "destroy", "terminate", "remove", "rm", "rmi", "reset", "clean", "prune", "push"}})
for tool in ("cloud", "kubernetes"):
    _POLICIES.update({(tool, action): classification for action, classification in (("status", OperationClass.READ), ("get", OperationClass.READ), ("list", OperationClass.READ), ("describe", OperationClass.READ), ("provision", OperationClass.WRITE), ("create", OperationClass.WRITE), ("update", OperationClass.WRITE), ("apply", OperationClass.WRITE), ("delete", OperationClass.DESTRUCTIVE), ("destroy", OperationClass.DESTRUCTIVE), ("remove", OperationClass.DESTRUCTIVE))})


def policy_for(tool: str, action: str) -> OperationPolicy:
    classification = _POLICIES.get((tool, action))
    if classification is None:
        raise UnknownOperationError(f"Unknown or unauthorized operation: {tool}.{action}")
    return OperationPolicy(tool=tool, action=action, classification=classification)


_SECRET_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)(aws_secret_access_key|aws_access_key_id|token|password|secret|api[_-]?key)(\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"\b(?:ghp|github_pat|sk|xox[baprs])_[A-Za-z0-9_-]+\b"),
)
_SECRET_KEY = re.compile(r"(?i)(?:^|[_-])(token|password|secret|api[_-]?key|authorization)(?:$|[_-])")


def redact_secrets(value: Any) -> Any:
    """Redact common secret forms recursively before a value crosses a boundary."""

    if isinstance(value, str):
        result = value
        for pattern in _SECRET_PATTERNS:
            result = pattern.sub(lambda match: f"{match.group(1) if match.lastindex else ''}{match.group(2) if match.lastindex and match.lastindex > 1 else ''}[REDACTED]", result)
        return result
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SECRET_KEY.search(str(key)) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(redact_secrets(item) for item in value)
    return value


__all__ = ["OperationClass", "OperationPolicy", "UnknownOperationError", "policy_for", "redact_secrets"]
