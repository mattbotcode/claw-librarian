"""Wikilink resolution for SystemVault."""

import re
from pathlib import Path

VAULT_ROOT = Path.home() / "SystemVault"

# Directories to exclude from scanning
EXCLUDE_DIRS = {"_inbox", "_librarian", "_templates", ".obsidian", "External Resources"}


def find_all_vault_files() -> list[Path]:
    """Return all .md files in the vault, excluding internal dirs."""
    results = []
    for path in VAULT_ROOT.rglob("*.md"):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        results.append(path)
    return results


def extract_wikilinks(text: str) -> list[str]:
    """Extract all [[wikilink]] targets from text.

    Handles [[target]], [[target|display]], and escaped pipes [[target\\|display]] forms.
    Also handles section links [[target#section]] by extracting just the target.
    """
    raw = re.findall(r"\[\[([^\]]+)\]\]", text)
    results = []
    for m in raw:
        # Handle escaped pipe (markdown table context) or regular pipe
        target = re.split(r"\\?\|", m)[0]
        # Strip section references
        target = target.split("#")[0]
        target = target.strip()
        if target:
            results.append(target)
    return results


def resolve_wikilink(name: str, vault_files: list[Path] | None = None) -> Path | None:
    """Resolve a wikilink name to a vault file path.

    Matches by stem (filename without extension), case-insensitive.
    """
    if vault_files is None:
        vault_files = find_all_vault_files()

    name_lower = name.lower().strip()
    for f in vault_files:
        if f.stem.lower() == name_lower:
            return f
    return None


def find_by_keyword(keyword: str, vault_files: list[Path] | None = None) -> list[Path]:
    """Find vault files whose frontmatter keywords contain the given term."""
    if vault_files is None:
        vault_files = find_all_vault_files()

    from .frontmatter import parse_file

    keyword_lower = keyword.lower()
    matches = []
    for f in vault_files:
        meta, _ = parse_file(f)
        if meta is None:
            continue
        kws = meta.get("keywords", [])
        if isinstance(kws, str):
            kws = [kws]
        if any(keyword_lower in kw.lower() for kw in kws):
            matches.append(f)
    return matches


def find_by_project(project: str, vault_files: list[Path] | None = None) -> Path | None:
    """Find the primary vault file for a project name.

    Tries: exact filename match, then keyword search.
    """
    if vault_files is None:
        vault_files = find_all_vault_files()

    # Try exact stem match first
    result = resolve_wikilink(project, vault_files)
    if result:
        return result

    # Try keyword match — return first match
    matches = find_by_keyword(project, vault_files)
    return matches[0] if matches else None


def incoming_links(target: Path, vault_files: list[Path] | None = None) -> list[Path]:
    """Find all vault files that link TO the given target via wikilinks."""
    if vault_files is None:
        vault_files = find_all_vault_files()

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
        if any(link.lower().strip() == target_stem for link in links):
            sources.append(f)
    return sources
