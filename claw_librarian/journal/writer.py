"""Journal writer — locked append to JSONL."""

from __future__ import annotations

import fcntl
import json
from datetime import datetime, timezone
from pathlib import Path

from ._ulid import generate_ulid
from .schema import JournalEntry, VALID_TYPES


def collect(
    journal_path: Path,
    agent: str,
    message: str,
    project: str | None = None,
    entry_type: str = "note",
    refs: list[str] | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> str:
    """Append a journal entry. Returns the entry ID (ULID).

    Acquires an exclusive lock on .journal.lock (shared with rotation)
    to prevent interleaved writes and mid-rotation corruption.
    """
    if entry_type not in VALID_TYPES:
        raise ValueError(f"Invalid entry type: {entry_type}")

    entry_id = generate_ulid()
    timestamp = datetime.now(timezone.utc).isoformat()

    entry = JournalEntry(
        schema_version=1,
        id=entry_id,
        timestamp=timestamp,
        agent=agent,
        type=entry_type,
        message=message,
        project=project,
        refs=refs or [],
        tags=tags or [],
        metadata=metadata or {},
    )

    line = entry.to_json_line() + "\n"

    # Ensure parent directory exists
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    lock_path = journal_path.parent / ".journal.lock"
    with open(lock_path, "a") as lock_fd:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        try:
            with open(journal_path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
        finally:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)

    return entry_id
