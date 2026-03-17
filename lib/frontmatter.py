"""YAML frontmatter parse/write utilities for SystemVault markdown files."""

import re
from datetime import date
from pathlib import Path

# Required fields for inbox entries
INBOX_REQUIRED = {"from", "date", "project", "action"}

# Required fields for vault notes (used by audit)
VAULT_REQUIRED = {"title", "keywords", "status", "type", "updated"}


def parse(text: str) -> tuple[dict | None, str]:
    """Parse YAML frontmatter from markdown text.

    Returns (metadata_dict, body) or (None, full_text) if no frontmatter.
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not match:
        return None, text

    raw_yaml = match.group(1)
    body = match.group(2)

    meta = {}
    for line in raw_yaml.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        # Handle YAML lists: [a, b, c]
        if value.startswith("[") and value.endswith("]"):
            value = [v.strip().strip('"').strip("'") for v in value[1:-1].split(",") if v.strip()]
        # Handle quoted strings
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
            lines.append(f"{key}: [{', '.join(value)}]")
        elif isinstance(value, date):
            lines.append(f"{key}: {value.isoformat()}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")

    # Ensure body doesn't start with extra blank lines
    body = body.lstrip("\n")
    lines.append(body)
    return "\n".join(lines)


def update_date(path: Path, field: str = "updated") -> None:
    """Update a date field in a vault file's frontmatter to today."""
    meta, body = parse_file(path)
    if meta is None:
        return
    meta[field] = date.today().isoformat()
    path.write_text(serialize(meta, body), encoding="utf-8")


def add_keywords(path: Path, new_keywords: list[str]) -> None:
    """Add keywords to a vault file's frontmatter (dedup)."""
    meta, body = parse_file(path)
    if meta is None:
        return
    existing = meta.get("keywords", [])
    if isinstance(existing, str):
        existing = [existing]
    merged = list(dict.fromkeys(existing + new_keywords))  # preserve order, dedup
    meta["keywords"] = merged
    path.write_text(serialize(meta, body), encoding="utf-8")


def validate_inbox(meta: dict | None) -> list[str]:
    """Return list of missing required fields for an inbox entry."""
    if meta is None:
        return ["no frontmatter found"]
    missing = INBOX_REQUIRED - set(meta.keys())
    return sorted(missing)


def validate_vault(meta: dict | None) -> list[str]:
    """Return list of missing required fields for a vault note."""
    if meta is None:
        return ["no frontmatter found"]
    missing = VAULT_REQUIRED - set(meta.keys())
    return sorted(missing)


# Skill-specific validation
SKILL_REQUIRED = VAULT_REQUIRED | {"domain", "source"}
SKILL_DOMAIN_REQUIRED = VAULT_REQUIRED | {"domain", "use_case"}


def validate_skill(meta: dict | None) -> list[str]:
    """Return list of missing required fields for a skill node."""
    if meta is None:
        return ["no frontmatter found"]
    missing = SKILL_REQUIRED - set(meta.keys())
    return sorted(missing)


def validate_skill_domain(meta: dict | None) -> list[str]:
    """Return list of missing required fields for a skill domain node."""
    if meta is None:
        return ["no frontmatter found"]
    missing = SKILL_DOMAIN_REQUIRED - set(meta.keys())
    return sorted(missing)
