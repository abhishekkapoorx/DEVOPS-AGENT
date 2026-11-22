"""Repository-backed Markdown documentation for the browser experience."""

from __future__ import annotations

from html import escape
from pathlib import Path
import re


DOCS = (
    {"slug": "cli", "group": "CLI", "title": "CLI overview", "file": "cli.md"},
    {"slug": "cli/authentication", "group": "CLI", "title": "Authentication", "file": "cli-authentication.md"},
    {"slug": "investigations", "group": "Investigation", "title": "How investigations work", "file": "investigations.md"},
    {"slug": "investigations/alertmanager", "group": "Investigation", "title": "Connect Alertmanager", "file": "alertmanager.md"},
)


def _render_markdown(source: str) -> str:
    """Render the small, trusted documentation corpus without template evaluation."""
    try:
        import markdown

        return markdown.markdown(source, extensions=["fenced_code", "tables", "toc"])
    except ImportError:
        result: list[str] = []
        in_code = False
        for line in source.splitlines():
            if line.startswith("```"):
                result.append("</code></pre>" if in_code else "<pre><code>")
                in_code = not in_code
            elif in_code:
                result.append(escape(line) + "\n")
            elif line.startswith("### "):
                result.append(f"<h3>{escape(line[4:])}</h3>")
            elif line.startswith("## "):
                result.append(f"<h2>{escape(line[3:])}</h2>")
            elif line.startswith("# "):
                result.append(f"<h1>{escape(line[2:])}</h1>")
            elif line:
                safe = escape(line)
                safe = re.sub(r"`([^`]+)`", r"<code>\1</code>", safe)
                result.append(f"<p>{safe}</p>")
        return "".join(result)


def load_doc(slug: str, docs_dir: Path) -> tuple[dict[str, str], str, int] | None:
    for index, item in enumerate(DOCS):
        if item["slug"] == slug:
            path = docs_dir / item["file"]
            return item, _render_markdown(path.read_text(encoding="utf-8")), index
    return None


__all__ = ["DOCS", "load_doc"]
