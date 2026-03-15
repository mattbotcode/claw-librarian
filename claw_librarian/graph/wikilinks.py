"""Wikilink extraction and resolution for Markdown vaults."""

from __future__ import annotations

import re
from pathlib import Path

EXCLUDE_DIRS = {"_inbox", "_librarian", "_templates", ".obsidian", "_processed", "_review"}


def find_all_vault_files(vault_root: Path) -> list[Path]:
    """Return all .md files in the vault, excluding internal dirs."""
    results = []
    for path in vault_root.rglob("*.md"):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        results.append(path)
    return results


def extract_wikilinks(text: str) -> list[str]:
    """Extract all [[wikilink]] targets from text.

    Handles [[target]], [[target|display]], and [[target#section]] forms.
    """
    raw = re.findall(r"\[\[([^\]]+)\]\]", text)
    results = []
    for m in raw:
        target = re.split(r"\\?\|", m)[0]
        target = target.split("#")[0].strip()
        if target:
            results.append(target)
    return results


def resolve_ref(ref: str, vault_root: Path, vault_files: list[Path] | None = None) -> Path | None:
    """Resolve a ref to a vault file.

    Resolution order:
    1. Literal vault-relative path: {vault_root}/{ref}.md
    2. Stem-only match (case-insensitive) for Obsidian compatibility
    """
    # Try literal path first — resolve and verify it stays inside vault_root
    literal = (vault_root / f"{ref}.md").resolve()
    try:
        literal.relative_to(vault_root.resolve())
    except ValueError:
        pass  # outside vault, skip literal branch
    else:
        if literal.exists():
            return literal

    # Fall back to stem matching
    if vault_files is None:
        vault_files = find_all_vault_files(vault_root)
    ref_stem = ref.lower().strip()
    # If ref has slashes, use just the last segment as stem
    if "/" in ref_stem:
        ref_stem = ref_stem.rsplit("/", 1)[-1]
    for f in vault_files:
        if f.stem.lower() == ref_stem:
            return f
    return None
