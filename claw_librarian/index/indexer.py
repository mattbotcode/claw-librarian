"""Main indexer — reads journal, builds materialized views."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from claw_librarian.config import Config
from claw_librarian.journal.reader import read_entries, read_entries_since
from claw_librarian.journal.schema import JournalEntry
from claw_librarian.index.map_builder import build_map
from claw_librarian.index.context_builder import build_context

DEFAULT_STATE = {
    "schema_version": 1,
    "last_indexed_id": "",
    "last_run": "",
    "last_rotation": "",
    "active_projects": [],
    "related_nodes": {},
}


def load_state(state_path: Path) -> dict:
    """Load indexer state, returning defaults if not found."""
    if not state_path.exists():
        return dict(DEFAULT_STATE)
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_STATE)


def save_state(state_path: Path, state: dict) -> None:
    """Save indexer state to disk."""
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def run_index(config: Config, full: bool = False) -> None:
    """Run the indexer: read journal, build MAP.md and context.md files."""
    state = load_state(config.state_path)

    # Read entries
    if full or not state["last_indexed_id"]:
        entries = list(read_entries(config.journal_path))
    else:
        entries = list(read_entries_since(
            config.journal_path, state["last_indexed_id"]
        ))

    # For MAP.md, we always need all entries (for accurate project/agent tables)
    all_entries = list(read_entries(config.journal_path))

    # Build MAP.md
    map_content = build_map(all_entries, config)
    config.map_path.write_text(map_content, encoding="utf-8")

    # Group entries by project for context building
    project_entries: dict[str, list[JournalEntry]] = defaultdict(list)
    for entry in all_entries:
        if entry.project:
            project_entries[entry.project].append(entry)

    # Collect related nodes from recent refs (with TTL)
    now = datetime.now(timezone.utc)
    ttl_seconds = config.related_node_ttl_hours * 3600
    related_by_project: dict[str, list[str]] = defaultdict(list)

    # Update related nodes from new entries
    related_nodes = state.get("related_nodes", {})
    for entry in entries:
        for ref in entry.refs:
            expires = now.timestamp() + ttl_seconds
            related_nodes[ref] = {
                "promoted_at": now.isoformat(),
                "expires_at": datetime.fromtimestamp(expires, tz=timezone.utc).isoformat(),
                "source_entries": related_nodes.get(ref, {}).get("source_entries", []) + [entry.id],
            }

    # Prune expired
    active_related = {}
    for ref, info in related_nodes.items():
        try:
            exp = datetime.fromisoformat(info["expires_at"].replace("Z", "+00:00"))
            if exp > now:
                active_related[ref] = info
                # Map ref to its project
                if "/" in ref:
                    parts = ref.split("/")
                    if len(parts) >= 2 and parts[0] == "projects":
                        proj = parts[1]
                        if ref not in related_by_project[proj]:
                            related_by_project[proj].append(ref)
        except (ValueError, KeyError):
            pass

    # Build per-project context files
    active_projects = []
    for project, proj_entries in project_entries.items():
        project_dir = config.projects_dir / project
        project_dir.mkdir(parents=True, exist_ok=True)
        ctx_content = build_context(
            project, proj_entries, config,
            related_nodes=related_by_project.get(project),
        )
        ctx_path = project_dir / config.context_file
        ctx_path.write_text(ctx_content, encoding="utf-8")
        active_projects.append(project)

    # Update state
    if all_entries:
        state["last_indexed_id"] = all_entries[-1].id
    state["last_run"] = now.isoformat()
    state["active_projects"] = sorted(active_projects)
    state["related_nodes"] = active_related
    save_state(config.state_path, state)
