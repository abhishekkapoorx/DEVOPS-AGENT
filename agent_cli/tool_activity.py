"""Textual widgets for in-line tool activity and result inspection."""

from __future__ import annotations

import json
import re
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Click
from textual.widgets import Static


class ToolActivityCard(Vertical, can_focus=True):
    """A focusable, two-stage disclosure for one Tool Call."""

    ALLOW_SELECT = True
    BINDINGS = [
        ("enter", "activate", "Expand tool activity"),
        ("space", "activate", "Expand tool activity"),
    ]
    DEFAULT_CSS = """
    ToolActivityCard {
        height: auto; margin: 0 0 1 0; padding: 0 1;
        border: round $accent; background: $surface; pointer: pointer;
    }
    ToolActivityCard:hover, ToolActivityCard:focus {
        border: round $accent;
        background: $panel;
    }
    .tool-activity-header {
        height: 3; padding: 0 1; background: $surface;
        align: left middle;
    }
    .tool-disclosure {
        width: 3; color: $accent; text-style: bold;
    }
    .tool-name {
        width: auto; color: $primary; text-style: bold;
    }
    .tool-status {
        width: 1fr; color: $text-muted; text-align: right;
    }
    .tool-activity-preview-panel {
        height: auto; max-height: 8; overflow-y: auto;
        margin: 0 1 1 1; padding: 0 1;
        border: round $surface; background: $panel;
    }
    .tool-activity-preview-label {
        height: 1; color: $text-muted; text-style: bold;
    }
    .tool-activity-preview {
        height: auto; color: $text;
    }
    """

    def __init__(self, call_id: str, name: str, status: str = "running") -> None:
        safe_call_id = re.sub(r"[^A-Za-z0-9_-]", "_", call_id)
        super().__init__(id=f"tool-{safe_call_id}", classes="tool-activity")
        self.call_id = call_id
        self.tool_name = name
        self.status = status
        self._expanded = False
        self._output_text: str | None = None
        self._preview_text = "Waiting for tool output…"

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Static("▸", classes="tool-disclosure"),
            Static(self.tool_name, classes="tool-name"),
            Static(self.status, classes="tool-status"),
            classes="tool-activity-header",
        )
        preview_panel = Vertical(
            Static("OUTPUT", classes="tool-activity-preview-label"),
            Static(Text(self._preview_text), classes="tool-activity-preview"),
            classes="tool-activity-preview-panel",
        )
        preview_panel.styles.display = "none"
        yield preview_panel

    def update_result(self, status: str, result: Any = None) -> None:
        self.status = status
        output_text = _format_tool_output(result)
        self._output_text = output_text
        self._preview_text = output_text if output_text is not None else "No output returned."
        if self.is_mounted:
            self.query_one(".tool-status", Static).update(self.status)
            self.query_one(".tool-activity-preview", Static).update(Text(self._preview_text))

    def on_click(self, event: Click) -> None:
        event.stop()
        self.action_activate()

    def action_activate(self) -> None:
        self._expanded = not self._expanded
        preview_panel = self.query_one(".tool-activity-preview-panel", Vertical)
        preview_panel.styles.display = "block" if self._expanded else "none"
        self.query_one(".tool-disclosure", Static).update("▾" if self._expanded else "▸")


def _format_tool_output(result: Any) -> str | None:
    if not isinstance(result, dict):
        return None
    output = result.get("output")
    error = result.get("error")
    sections: list[str] = []
    if output is not None:
        if isinstance(output, str):
            sections.append(output)
        else:
            try:
                sections.append(json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True))
            except (TypeError, ValueError):
                sections.append(str(output))
    if error:
        sections.append(f"Error: {error}")
    return "\n\n".join(sections) if sections else None


__all__ = ["ToolActivityCard"]
