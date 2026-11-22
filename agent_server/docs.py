"""Repository-backed Markdown documentation for the browser experience."""

from __future__ import annotations

from html import escape, unescape
from pathlib import Path
import re


DOCS = (
    {
        "slug": "cli",
        "group": "CLI",
        "title": "CLI overview",
        "file": "cli.md",
    },
    {
        "slug": "cli/authentication",
        "group": "CLI",
        "title": "Authentication",
        "file": "cli-authentication.md",
    },
    {
        "slug": "cli/slash-commands",
        "group": "CLI",
        "title": "Slash commands",
        "file": "cli-slash-commands.md",
    },
    {
        "slug": "cli/tools/aws",
        "group": "CLI tools",
        "title": "AWS CLI",
        "file": "cli-tool-aws.md",
    },
    {
        "slug": "cli/tools/az",
        "group": "CLI tools",
        "title": "Azure CLI",
        "file": "cli-tool-az.md",
    },
    {
        "slug": "cli/tools/gcloud",
        "group": "CLI tools",
        "title": "Google Cloud CLI",
        "file": "cli-tool-gcloud.md",
    },
    {
        "slug": "cli/tools/kubectl",
        "group": "CLI tools",
        "title": "kubectl",
        "file": "cli-tool-kubectl.md",
    },
    {
        "slug": "cli/tools/docker",
        "group": "CLI tools",
        "title": "Docker CLI",
        "file": "cli-tool-docker.md",
    },
    {
        "slug": "cli/tools/git",
        "group": "CLI tools",
        "title": "Git",
        "file": "cli-tool-git.md",
    },
    {
        "slug": "cli/tools/files",
        "group": "CLI tools",
        "title": "Workspace files",
        "file": "cli-tool-files.md",
    },
    {
        "slug": "investigations",
        "group": "Investigation",
        "title": "Investigation Agent",
        "file": "investigations.md",
    },
    {
        "slug": "investigations/alertmanager",
        "group": "Investigation",
        "title": "Connect Alertmanager",
        "file": "alertmanager.md",
    },
    {
        "slug": "investigations/slack",
        "group": "Investigation",
        "title": "Connect Slack",
        "file": "slack.md",
    },
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
                safe = re.sub(
                    r"\[([^\]]+)\]\(([^)]+)\)",
                    _render_link,
                    safe,
                )
                safe = re.sub(r"`([^`]+)`", r"<code>\1</code>", safe)
                result.append(f"<p>{safe}</p>")
        return "".join(result)


def _render_link(match: re.Match[str]) -> str:
    target = unescape(match.group(2))
    if not (
        (target.startswith("/") and not target.startswith("//"))
        or target.startswith("https://")
    ):
        return match.group(0)
    return f'<a href="{escape(target, quote=True)}">{match.group(1)}</a>'


def load_doc(slug: str, docs_dir: Path) -> tuple[dict[str, str], str, int] | None:
    for index, item in enumerate(DOCS):
        if item["slug"] == slug:
            path = docs_dir / item["file"]
            return item, _render_markdown(path.read_text(encoding="utf-8")), index
    return None


__all__ = ["DOCS", "load_doc"]
