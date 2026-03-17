#!/usr/bin/env python3
"""CC Memory → SystemVault sync.

Compares Claude Code memory files against vault notes by modification date.
When CC memory is newer, writes an inbox entry so process_inbox.py handles the merge.

Runs at 3 AM via cron.
"""

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.frontmatter import parse_file
from lib.wikilinks import find_by_project, VAULT_ROOT

CC_MEMORY_DIR = Path.home() / ".claude" / "projects" / "-mnt-c-Users-mattg" / "memory"
INBOX = VAULT_ROOT / "_inbox"

# Map CC memory subdirectory names to vault project paths
# (only needed when the names don't match; find_by_project handles the rest)


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def get_vault_updated(vault_path: Path) -> date | None:
    """Get the 'updated' date from a vault file's frontmatter."""
    if not vault_path.exists():
        return None
    meta, _ = parse_file(vault_path)
    if meta and "updated" in meta:
        try:
            return date.fromisoformat(str(meta["updated"]))
        except (ValueError, TypeError):
            return None
    return None


def get_file_mtime(path: Path) -> date:
    """Get a file's modification date."""
    return datetime.fromtimestamp(path.stat().st_mtime).date()


def diff_content(cc_text: str, vault_text: str) -> str:
    """Simple diff — return lines in CC memory not present in vault note."""
    vault_lines = set(vault_text.splitlines())
    new_lines = []
    for line in cc_text.splitlines():
        stripped = line.strip()
        if stripped and stripped not in vault_lines and not stripped.startswith("---"):
            new_lines.append(line)
    if not new_lines:
        return ""
    return "\n".join(new_lines)


def write_inbox_entry(project: str, vault_path: Path, diff: str) -> Path:
    """Write an inbox entry for the sync."""
    today = date.today().isoformat()
    slug = project.lower().replace(" ", "-")
    filename = f"{today}-claude-code-sync-{slug}.md"
    entry_path = INBOX / filename

    rel_target = vault_path.relative_to(VAULT_ROOT)
    content = f"""---
from: claude-code
date: {today}
project: {project}
action: update
target: {rel_target}
---

## What Changed (CC Memory Sync)

{diff.strip()}
"""
    entry_path.write_text(content, encoding="utf-8")
    return entry_path


def scan_memory_files() -> list[Path]:
    """Find all .md files in CC memory (excluding MEMORY.md index)."""
    if not CC_MEMORY_DIR.exists():
        return []
    results = []
    for f in CC_MEMORY_DIR.rglob("*.md"):
        if f.name == "MEMORY.md":
            continue
        results.append(f)
    return results


def main() -> None:
    log("Starting CC memory sync")

    INBOX.mkdir(parents=True, exist_ok=True)
    memory_files = scan_memory_files()

    if not memory_files:
        log("No CC memory files found")
        return

    log(f"Found {len(memory_files)} CC memory file(s)")
    synced = 0

    for mem_file in memory_files:
        # Derive project name from path or filename
        # e.g., memory/projects/macro-model.md → "macro-model"
        # or memory/feedback_testing.md → skip (not a project file)
        rel = mem_file.relative_to(CC_MEMORY_DIR)

        # Only sync project-related files
        # Look for files in projects/ subdirectory or files with project-like names
        project_name = mem_file.stem

        # Try to find matching vault file
        vault_path = find_by_project(project_name)
        if vault_path is None:
            continue

        # Compare dates
        mem_mtime = get_file_mtime(mem_file)
        vault_updated = get_vault_updated(vault_path)

        if vault_updated is None or mem_mtime > vault_updated:
            # CC memory is newer — compute diff
            cc_text = mem_file.read_text(encoding="utf-8")
            vault_text = vault_path.read_text(encoding="utf-8")
            diff = diff_content(cc_text, vault_text)

            if not diff.strip():
                continue

            entry = write_inbox_entry(project_name, vault_path, diff)
            log(f"  Synced: {project_name} → {entry.name}")
            synced += 1

    log(f"Sync complete: {synced} inbox entry/entries created")


if __name__ == "__main__":
    main()
