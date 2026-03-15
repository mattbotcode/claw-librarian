"""Journal rotation — monthly rename + summary generation."""

from __future__ import annotations

import fcntl
import shutil
from datetime import date, timedelta
from pathlib import Path

from claw_librarian.config import Config


def needs_rotation(last_rotation: str) -> bool:
    """Check if journal needs rotation based on last rotation month."""
    current_month = date.today().strftime("%Y-%m")
    return last_rotation != current_month


def _previous_month() -> str:
    """Get YYYY-MM for the previous month (the month being archived)."""
    first_of_month = date.today().replace(day=1)
    last_of_prev = first_of_month - timedelta(days=1)
    return last_of_prev.strftime("%Y-%m")


def rotate_journal(config: Config, state: dict) -> None:
    """Rotate journal.jsonl to journal-YYYY-MM.jsonl if needed.

    Uses a lock file to coordinate with concurrent writers. The
    sequence is:
    1. Acquire exclusive lock on .journal.lock
    2. Copy journal.jsonl → journal-YYYY-MM.jsonl (previous month)
    3. Truncate journal.jsonl to empty
    4. Release lock
    This avoids the rename-while-locked pitfall (fcntl locks are
    bound to fd, not path).
    """
    if not needs_rotation(state.get("last_rotation", "")):
        return

    journal = config.journal_path
    if not journal.exists() or journal.stat().st_size == 0:
        state["last_rotation"] = date.today().strftime("%Y-%m")
        return

    prev_month = _previous_month()
    archive_name = f"journal-{prev_month}.jsonl"
    archive_path = journal.parent / archive_name
    lock_path = journal.parent / ".journal.lock"

    # Lock, copy, truncate, unlock
    lock_path.touch()
    with open(lock_path, "r") as lock_fd:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        try:
            shutil.copy2(journal, archive_path)
            journal.write_text("")
        finally:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)

    state["last_rotation"] = date.today().strftime("%Y-%m")
