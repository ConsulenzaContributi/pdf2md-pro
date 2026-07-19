"""Composizione e scrittura del Markdown finale con frontmatter YAML."""

from __future__ import annotations

import json
from pathlib import Path


def render_frontmatter(fields: dict) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, str):
            value = json.dumps(value, ensure_ascii=False)
        lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_output(markdown: str, frontmatter: dict, out_md: Path) -> None:
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(render_frontmatter(frontmatter) + markdown, encoding="utf-8")
