"""YAML frontmatter parse/write utilities for Markdown files."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path


def parse(text: str) -> tuple[dict | None, str]:
    """Parse YAML frontmatter from markdown text.

    Returns (metadata_dict, body) or (None, full_text) if no frontmatter.
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not match:
        return None, text

    raw_yaml = match.group(1)
    body = match.group(2)

    meta: dict = {}
    for line in raw_yaml.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            value = [
                v.strip().strip('"').strip("'")
                for v in value[1:-1].split(",")
                if v.strip()
            ]
        elif value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        meta[key] = value

    return meta, body


def parse_file(path: Path) -> tuple[dict | None, str]:
    """Parse frontmatter from a file path."""
    text = path.read_text(encoding="utf-8")
    return parse(text)


def serialize(meta: dict, body: str) -> str:
    """Serialize metadata dict + body back to frontmatter markdown."""
    lines = ["---"]
    for key, value in meta.items():
        if isinstance(value, list):
            lines.append(f"{key}: [{', '.join(str(v) for v in value)}]")
        elif isinstance(value, date):
            lines.append(f"{key}: {value.isoformat()}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    body = body.lstrip("\n")
    lines.append(body)
    return "\n".join(lines)
