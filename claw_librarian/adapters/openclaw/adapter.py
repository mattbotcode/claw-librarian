"""OpenClaw adapter — inbox bridge, agent identity, config preset."""

from __future__ import annotations

from pathlib import Path

from claw_librarian.config import Config, load_config
from claw_librarian.graph.frontmatter import parse_file, parse, serialize
from claw_librarian.journal.writer import collect


# Map inbox 'action' to journal event types
ACTION_TO_TYPE = {
    "update": "milestone",
    "create": "milestone",
    "log": "note",
}


class OpenClawAdapter:
    """Adapter for the OpenClaw/SystemVault ecosystem."""

    def __init__(self, vault_root: Path) -> None:
        self.vault_root = vault_root
        self.config = load_config(vault_root=vault_root)

    def bridge_inbox(self) -> list[str]:
        """Process all pending inbox files. Returns list of journal entry IDs.

        Scans both _inbox/ (unprocessed) and _inbox/_processed/ (already
        routed by process_inbox.py). Files already stamped with journal_id
        are skipped.
        """
        inbox_dir = self.vault_root / "_inbox"
        if not inbox_dir.exists():
            return []
        entry_ids = []
        # Scan live inbox first, then processed
        dirs = [inbox_dir, inbox_dir / "_processed"]
        for d in dirs:
            if not d.exists():
                continue
            for f in sorted(d.glob("*.md")):
                entry_id = bridge_inbox_file(f, self.config)
                if entry_id:
                    entry_ids.append(entry_id)
        return entry_ids


def bridge_inbox_file(inbox_file: Path, config: Config) -> str | None:
    """Bridge a single inbox .md file into the journal.

    Returns the journal entry ID, or None if skipped.
    """
    meta, body = parse_file(inbox_file)
    if meta is None:
        return None

    # Skip already-stamped files
    if "journal_id" in meta:
        return None

    # Extract fields
    agent = meta.get("from", "unknown")
    project = meta.get("project")
    action = meta.get("action", "note")
    entry_type = ACTION_TO_TYPE.get(action, "note")
    message = body.strip()
    if not message:
        message = f"[{action}] from {agent}"

    entry_id = collect(
        journal_path=config.journal_path,
        agent=agent,
        message=message,
        project=project,
        entry_type=entry_type,
    )

    # Stamp the inbox file with journal_id
    meta["journal_id"] = entry_id
    stamped = serialize(meta, body)
    inbox_file.write_text(stamped, encoding="utf-8")

    return entry_id


def discover_agents(vault_root: Path) -> list[str]:
    """Discover agent names from team/*.md files."""
    team_dir = vault_root / "team"
    if not team_dir.exists():
        return []
    return [f.stem for f in team_dir.glob("*.md")]
