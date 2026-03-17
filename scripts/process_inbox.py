#!/usr/bin/env python3
"""Process SystemVault inbox entries — parse, route, merge, move.

Runs every 30 minutes via cron. No LLM involved — pure structured text manipulation.
"""

import shutil
import sys
import time
from datetime import date, datetime
from pathlib import Path

# Add parent to path for lib imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.frontmatter import parse_file, validate_inbox, parse, serialize
from lib.wikilinks import find_by_project, VAULT_ROOT

INBOX = VAULT_ROOT / "_inbox"
PROCESSED = INBOX / "_processed"
REVIEW = INBOX / "_review"
RETENTION_DAYS = 7


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def handle_update(meta: dict, body: str, source: Path) -> bool:
    """Append content to an existing vault file under a dated ### Update section."""
    target_path = None

    # Try explicit target first
    if "target" in meta:
        candidate = VAULT_ROOT / meta["target"]
        if candidate.exists():
            target_path = candidate

    # Fall back to project keyword search
    if target_path is None:
        project = meta.get("project", "")
        target_path = find_by_project(project)

    if target_path is None:
        log(f"  No matching vault file for project '{meta.get('project', '?')}' — moving to _review")
        return False

    # Read existing content
    target_meta, target_body = parse_file(target_path)

    # Build update section
    from_agent = meta.get("from", "unknown")
    update_date = meta.get("date", date.today().isoformat())
    update_section = f"\n\n### Update ({update_date}, {from_agent})\n\n{body.strip()}\n"

    # Append to body
    new_body = target_body.rstrip() + update_section

    # Update the 'updated' date in frontmatter
    if target_meta:
        target_meta["updated"] = date.today().isoformat()
        content = serialize(target_meta, new_body)
    else:
        content = new_body

    target_path.write_text(content, encoding="utf-8")

    # Add keywords if provided
    if "keywords" in meta and target_meta:
        kws = meta["keywords"]
        if isinstance(kws, str):
            kws = [kws]
        from lib.frontmatter import add_keywords
        add_keywords(target_path, kws)

    log(f"  Updated: {target_path.relative_to(VAULT_ROOT)}")
    return True


def handle_create(meta: dict, body: str, source: Path) -> bool:
    """Create a new vault file. If it already exists, treat as update."""
    project = meta.get("project", "misc")
    title = meta.get("title", source.stem)

    # Determine target path
    if "target" in meta:
        target_path = VAULT_ROOT / meta["target"]
    else:
        # Slug from title
        slug = title.lower().replace(" ", "-")
        target_path = VAULT_ROOT / project / f"{slug}.md"

    # If file exists, treat as update
    if target_path.exists():
        log(f"  File already exists, treating as update: {target_path.relative_to(VAULT_ROOT)}")
        return handle_update(meta, body, source)

    # Ensure parent directory exists
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Build frontmatter for new file — enforce standard property schema
    note_type = meta.get("type", "project")
    new_meta = {
        "title": title,
        "keywords": meta.get("keywords", [project]),
        "status": meta.get("status", "active"),
        "type": note_type,
        "updated": date.today().isoformat(),
    }

    # Add project-level properties
    if note_type in ("project", "lesson", "lessons"):
        new_meta["priority"] = meta.get("priority", "medium")
        new_meta["owner"] = meta.get("owner", meta.get("from", "kingpin"))
        new_meta["last_reviewed"] = date.today().isoformat()

    # Add lessons-specific properties
    if note_type in ("lesson", "lessons"):
        new_meta["project"] = project
        new_meta["last_updated"] = date.today().isoformat()

    content = serialize(new_meta, body.strip() + "\n")
    target_path.write_text(content, encoding="utf-8")
    log(f"  Created: {target_path.relative_to(VAULT_ROOT)}")
    return True


def handle_log(meta: dict, body: str, source: Path) -> bool:
    """Append to a project changelog."""
    project = meta.get("project", "misc")
    changelog_path = VAULT_ROOT / project / "changelog" / "changelog.md"

    if not changelog_path.exists():
        changelog_path.parent.mkdir(parents=True, exist_ok=True)
        header_meta = {
            "title": f"{project} Changelog",
            "keywords": [project, "changelog"],
            "status": "active",
            "type": "log",
            "updated": date.today().isoformat(),
        }
        content = serialize(header_meta, f"# {project} — Changelog\n")
        changelog_path.write_text(content, encoding="utf-8")

    # Append log entry
    from_agent = meta.get("from", "unknown")
    entry_date = meta.get("date", date.today().isoformat())
    entry = f"\n### {entry_date} — {from_agent}\n\n{body.strip()}\n"

    existing = changelog_path.read_text(encoding="utf-8")
    changelog_path.write_text(existing.rstrip() + entry + "\n", encoding="utf-8")

    # Update frontmatter date
    from lib.frontmatter import update_date
    update_date(changelog_path)

    log(f"  Logged to: {changelog_path.relative_to(VAULT_ROOT)}")
    return True


ACTION_HANDLERS = {
    "update": handle_update,
    "create": handle_create,
    "log": handle_log,
}


def process_entry(path: Path) -> None:
    """Process a single inbox entry."""
    log(f"Processing: {path.name}")

    meta, body = parse_file(path)

    # Validate required fields
    errors = validate_inbox(meta)
    if errors:
        log(f"  Validation failed (missing: {', '.join(errors)}) — moving to _review")
        shutil.move(str(path), str(REVIEW / path.name))
        return

    action = meta["action"]
    handler = ACTION_HANDLERS.get(action)
    if handler is None:
        log(f"  Unknown action '{action}' — moving to _review")
        shutil.move(str(path), str(REVIEW / path.name))
        return

    success = handler(meta, body, path)
    if success:
        shutil.move(str(path), str(PROCESSED / path.name))
    else:
        shutil.move(str(path), str(REVIEW / path.name))


def cleanup_processed() -> None:
    """Remove processed files older than RETENTION_DAYS."""
    cutoff = time.time() - (RETENTION_DAYS * 86400)
    removed = 0
    for f in PROCESSED.glob("*.md"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            removed += 1
    if removed:
        log(f"Cleaned up {removed} old processed file(s)")


def main() -> None:
    # Ensure directories exist
    PROCESSED.mkdir(parents=True, exist_ok=True)
    REVIEW.mkdir(parents=True, exist_ok=True)

    # Process inbox entries
    entries = sorted(INBOX.glob("*.md"))
    if entries:
        log(f"Found {len(entries)} inbox entry/entries")
        for entry in entries:
            try:
                process_entry(entry)
            except Exception as e:
                log(f"  ERROR processing {entry.name}: {e}")
                try:
                    shutil.move(str(entry), str(REVIEW / entry.name))
                except Exception:
                    pass
    else:
        log("Inbox empty — nothing to process")

    # Always run cleanup regardless of inbox state
    cleanup_processed()


if __name__ == "__main__":
    main()
