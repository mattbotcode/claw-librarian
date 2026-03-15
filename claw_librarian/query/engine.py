"""Query engine — search journal + vault, rank by freshness."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from claw_librarian.config import Config
from claw_librarian.journal.reader import read_entries, filter_entries
from claw_librarian.graph.wikilinks import find_all_vault_files


@dataclass
class SearchResult:
    """A single search result."""
    source_type: str  # "journal" or "vault"
    message: str
    timestamp: str
    agent: str | None = None
    project: str | None = None
    file_path: str | None = None
    line_num: int | None = None
    entry_id: str | None = None
    refs: list[str] | None = None
    link_density: int = 0


def search(
    query: str,
    config: Config,
    *,
    project: str | None = None,
    agent: str | None = None,
    since: str | None = None,
    depth: int | None = None,
) -> list[SearchResult]:
    """Search journal and vault Markdown files.

    Returns results sorted by freshness (newest first).
    """
    results: list[SearchResult] = []
    pattern = re.compile(re.escape(query), re.IGNORECASE) if query else None

    # Phase 1a: Search journal
    entries = filter_entries(
        read_entries(config.journal_path),
        project=project,
        agent=agent,
        since=since,
    )
    for entry in entries:
        if pattern is None or pattern.search(entry.message) or any(
            pattern.search(t) for t in entry.tags
        ):
            results.append(SearchResult(
                source_type="journal",
                message=entry.message,
                timestamp=entry.timestamp,
                agent=entry.agent,
                project=entry.project,
                entry_id=entry.id,
                refs=entry.refs,
            ))

    # Phase 1b: Search vault Markdown files
    if query:  # Only grep vault if there's a search term
        vault_files = find_all_vault_files(config.vault_root)
        for f in vault_files:
            try:
                text = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for line_num, line in enumerate(text.split("\n"), 1):
                if pattern.search(line):
                    rel_path = str(f.relative_to(config.vault_root))
                    results.append(SearchResult(
                        source_type="vault",
                        message=line.strip(),
                        timestamp="",  # vault files don't have per-line timestamps
                        file_path=rel_path,
                        line_num=line_num,
                    ))
                    break  # One hit per file

    # Sort: journal hits by freshness, vault hits after
    journal_hits = sorted(
        [r for r in results if r.source_type == "journal"],
        key=lambda r: r.timestamp,
        reverse=True,
    )
    vault_hits = [r for r in results if r.source_type == "vault"]

    return journal_hits + vault_hits
