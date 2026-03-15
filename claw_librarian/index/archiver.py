"""Context archival and re-hydration."""

from __future__ import annotations

from pathlib import Path

from claw_librarian.config import Config


def archive_context(project: str, config: Config, month_label: str) -> Path | None:
    """Snapshot a project's context.md into archive/context-YYYY-MM.md."""
    ctx_path = config.projects_dir / project / config.context_file
    if not ctx_path.exists():
        return None

    archive_dir = config.projects_dir / project / config.archive_dir
    archive_dir.mkdir(parents=True, exist_ok=True)

    archive_path = archive_dir / f"context-{month_label}.md"
    content = ctx_path.read_text(encoding="utf-8")
    archive_path.write_text(content, encoding="utf-8")
    return archive_path


def rehydrate_context(project: str, config: Config) -> str | None:
    """Load the most recent archived context for a project.

    Returns the content string or None if no archive exists.
    """
    archive_dir = config.projects_dir / project / config.archive_dir
    if not archive_dir.exists():
        return None

    archives = sorted(archive_dir.glob("context-*.md"), reverse=True)
    if not archives:
        return None

    return archives[0].read_text(encoding="utf-8")
