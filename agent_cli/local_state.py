"""Non-secret local CLI state used only to reopen the last selected conversation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol


class ConversationSelectionStore(Protocol):
    def load(self) -> str | None: ...
    def save(self, conversation_id: str) -> None: ...
    def clear(self) -> None: ...


class JsonConversationSelectionStore:
    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            if os.name == "nt":
                root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
            else:
                root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
            path = root / "devops-agent" / "conversation.json"
        self.path = path

    def load(self) -> str | None:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        if not isinstance(value, dict) or not isinstance(value.get("conversation_id"), str):
            return None
        return value["conversation_id"]

    def save(self, conversation_id: str) -> None:
        if not conversation_id:
            raise ValueError("conversation id is required")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"conversation_id": conversation_id}, separators=(",", ":")),
            encoding="utf-8",
        )
        if os.name != "nt":
            os.chmod(temporary, 0o600)
        temporary.replace(self.path)

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


__all__ = ["ConversationSelectionStore", "JsonConversationSelectionStore"]
