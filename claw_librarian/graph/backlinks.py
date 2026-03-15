"""Reverse link index — find all files that link TO a given target."""

from __future__ import annotations

from pathlib import Path

from .wikilinks import find_all_vault_files, extract_wikilinks, resolve_ref


def build_backlink_index(vault_root: Path) -> dict[Path, list[Path]]:
    """Build a map of target -> [source files that link to it]."""
    vault_files = find_all_vault_files(vault_root)
    index: dict[Path, list[Path]] = {}

    for source in vault_files:
        try:
            text = source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        links = extract_wikilinks(text)
        for link in links:
            target = resolve_ref(link, vault_root, vault_files)
            if target and target != source:
                index.setdefault(target, []).append(source)

    return index


def incoming_links(
    target: Path,
    vault_root: Path,
    vault_files: list[Path] | None = None,
) -> list[Path]:
    """Find all vault files that link TO the given target."""
    if vault_files is None:
        vault_files = find_all_vault_files(vault_root)

    if not target.exists():
        return []

    target_stem = target.stem.lower()
    sources = []
    for f in vault_files:
        if f == target:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        links = extract_wikilinks(text)
        for link in links:
            link_stem = link.lower().strip()
            if "/" in link_stem:
                link_stem = link_stem.rsplit("/", 1)[-1]
            if link_stem == target_stem:
                sources.append(f)
                break
    return sources
