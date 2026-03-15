"""Journal reader — stream, filter, and query JSONL entries."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path

from .schema import JournalEntry


def read_entries(journal_path: Path) -> Iterator[JournalEntry]:
    """Stream all valid entries from a journal file. Skips malformed lines."""
    if not journal_path.exists():
        return
    with open(journal_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = JournalEntry.from_json_line(line)
                yield entry
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                print(
                    f"warning: skipping malformed line {line_num} in "
                    f"{journal_path.name}: {e}",
                    file=sys.stderr,
                )


def read_entries_since(
    journal_path: Path, since_id: str
) -> Iterator[JournalEntry]:
    """Yield entries that come AFTER the given ID (exclusive)."""
    found = False
    for entry in read_entries(journal_path):
        if found:
            yield entry
        elif entry.id == since_id:
            found = True


def filter_entries(
    entries: Iterator[JournalEntry],
    *,
    project: str | None = None,
    agent: str | None = None,
    entry_type: str | None = None,
    since: str | None = None,
) -> Iterator[JournalEntry]:
    """Filter an entry stream by project, agent, type, or date."""
    for entry in entries:
        if project and entry.project != project:
            continue
        if agent and entry.agent != agent:
            continue
        if entry_type and entry.type != entry_type:
            continue
        if since and entry.timestamp < since:
            continue
        yield entry
