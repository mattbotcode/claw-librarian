#!/usr/bin/env python3
"""Daily SystemVault audit — checks frontmatter, wikilinks, staleness, orphans.

Runs at 2 AM via cron. Writes report to _librarian/reports/ and sends Telegram if issues found.
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.frontmatter import parse_file, validate_vault, validate_skill, validate_skill_domain
from lib.wikilinks import find_all_vault_files, extract_wikilinks, resolve_wikilink, incoming_links
from lib.telegram import send_message
from validate_canvas import validate_all_canvases

VAULT_ROOT = Path.home() / "SystemVault"
REPORTS_DIR = VAULT_ROOT / "_librarian" / "reports"
SKILLS_SHARED = Path.home() / ".openclaw" / "skills-shared"
MANIFEST_PATHS = [
    Path.home() / ".openclaw" / "workspace" / "manifest.md",
    Path.home() / ".openclaw" / "workspace-optic" / "manifest.md",
    Path.home() / ".openclaw" / "workspace-security" / "manifest.md",
]
STALE_DAYS = 30
REPORT_RETENTION_DAYS = 30


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def run_audit() -> dict:
    """Run all audit checks. Returns dict of issue lists."""
    vault_files = find_all_vault_files()
    log(f"Scanning {len(vault_files)} vault files")

    issues = {
        "missing_frontmatter": [],
        "stale": [],
        "broken_wikilinks": [],
        "orphans": [],
        "broken_skill_sources": [],
        "skill_frontmatter": [],
        "orphaned_skills": [],
        "manifest_issues": [],
        "broken_canvas_links": [],
    }

    today = date.today()
    stale_cutoff = today - timedelta(days=STALE_DAYS)

    for f in vault_files:
        rel = f.relative_to(VAULT_ROOT)
        meta, body = parse_file(f)

        # Check frontmatter
        missing = validate_vault(meta)
        if missing:
            issues["missing_frontmatter"].append((str(rel), missing))

        # Check staleness
        if meta and "updated" in meta:
            try:
                updated = date.fromisoformat(str(meta["updated"]))
                if updated < stale_cutoff:
                    days_old = (today - updated).days
                    issues["stale"].append((str(rel), days_old))
            except (ValueError, TypeError):
                pass

        # Check wikilinks
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        links = extract_wikilinks(text)
        for link in links:
            target = resolve_wikilink(link, vault_files)
            if target is None:
                issues["broken_wikilinks"].append((str(rel), link))

        # Check orphans (files with zero incoming links)
        inbound = incoming_links(f, vault_files)
        if not inbound:
            # Exclude index files from orphan check
            if f.name not in ("vault-index.md",):
                issues["orphans"].append(str(rel))

    # Skill-specific checks
    for f in vault_files:
        rel = f.relative_to(VAULT_ROOT)
        meta, _ = parse_file(f)
        if meta is None:
            continue

        note_type = meta.get("type", "")

        # Validate skill node frontmatter
        if note_type == "skill":
            missing = validate_skill(meta)
            if missing:
                issues["skill_frontmatter"].append((str(rel), missing))
            # Check source path exists
            source = meta.get("source", "")
            if source:
                source_path = Path(str(source).replace("~", str(Path.home())))
                if not source_path.exists():
                    issues["broken_skill_sources"].append((str(rel), str(source)))

        elif note_type == "skill-domain":
            missing = validate_skill_domain(meta)
            if missing:
                issues["skill_frontmatter"].append((str(rel), missing))

    # Check for orphaned shared skills (SKILL.md with no vault node)
    if SKILLS_SHARED.exists():
        vault_sources = set()
        for f in vault_files:
            meta, _ = parse_file(f)
            if meta and meta.get("type") == "skill" and "source" in meta:
                vault_sources.add(str(meta["source"]).replace("~", str(Path.home())))

        for skill_md in SKILLS_SHARED.rglob("SKILL.md"):
            if skill_md.parent.name == "_template":
                continue
            if str(skill_md) not in vault_sources:
                issues["orphaned_skills"].append(str(skill_md.relative_to(SKILLS_SHARED)))
        # Also check lowercase skill.md
        for skill_md in SKILLS_SHARED.rglob("skill.md"):
            if skill_md.parent.name == "_template":
                continue
            if str(skill_md) not in vault_sources:
                issues["orphaned_skills"].append(str(skill_md.relative_to(SKILLS_SHARED)))

    # Manifest validation
    for manifest_path in MANIFEST_PATHS:
        if not manifest_path.exists():
            continue
        manifest_meta, manifest_body = parse_file(manifest_path)
        agent = manifest_meta.get("agent", "unknown") if manifest_meta else "unknown"
        links = extract_wikilinks(manifest_body)
        for link in links:
            target = resolve_wikilink(link, vault_files)
            if target is None:
                issues["manifest_issues"].append((agent, link))

    # Canvas validation — check that canvas nodes resolve to vault .md files
    canvas_results = validate_all_canvases(vault_files)
    for canvas_path, result in canvas_results.items():
        if "error" in result:
            issues["broken_canvas_links"].append((canvas_path, f"parse error: {result['error']}"))
        for node_id, name in result.get("broken", []):
            issues["broken_canvas_links"].append((canvas_path, name))

    return issues


def write_report(issues: dict) -> Path:
    """Write audit report to _librarian/reports/."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    report_path = REPORTS_DIR / f"audit-{today}.md"

    total = sum(len(v) for v in issues.values())

    lines = [
        f"---",
        f"title: Vault Audit — {today}",
        f"type: report",
        f"updated: {today}",
        f"---",
        f"",
        f"# Vault Audit — {today}",
        f"",
        f"**Total issues: {total}**",
        f"",
    ]

    # Missing frontmatter
    items = issues["missing_frontmatter"]
    lines.append(f"## Missing Frontmatter ({len(items)})")
    lines.append("")
    if items:
        for path, missing in items:
            lines.append(f"- `{path}` — missing: {', '.join(missing)}")
    else:
        lines.append("None.")
    lines.append("")

    # Stale notes
    items = issues["stale"]
    lines.append(f"## Stale Notes ({len(items)})")
    lines.append("")
    if items:
        for path, days in sorted(items, key=lambda x: -x[1]):
            lines.append(f"- `{path}` — {days} days since update")
    else:
        lines.append("None.")
    lines.append("")

    # Broken wikilinks
    items = issues["broken_wikilinks"]
    lines.append(f"## Broken Wikilinks ({len(items)})")
    lines.append("")
    if items:
        for path, link in items:
            lines.append(f"- `{path}` → `[[{link}]]`")
    else:
        lines.append("None.")
    lines.append("")

    # Orphans
    items = issues["orphans"]
    lines.append(f"## Orphan Notes ({len(items)})")
    lines.append("")
    if items:
        for path in sorted(items):
            lines.append(f"- `{path}`")
    else:
        lines.append("None.")
    lines.append("")

    # Skills section
    lines.append("---")
    lines.append("")
    lines.append("# Skills")
    lines.append("")

    items = issues["broken_skill_sources"]
    lines.append(f"## Broken Skill Sources ({len(items)})")
    lines.append("")
    if items:
        for path, source in items:
            lines.append(f"- `{path}` → `{source}` (file not found)")
    else:
        lines.append("None.")
    lines.append("")

    items = issues["skill_frontmatter"]
    lines.append(f"## Skill Frontmatter Issues ({len(items)})")
    lines.append("")
    if items:
        for path, missing in items:
            lines.append(f"- `{path}` — missing: {', '.join(missing)}")
    else:
        lines.append("None.")
    lines.append("")

    items = issues["orphaned_skills"]
    lines.append(f"## Orphaned Shared Skills ({len(items)})")
    lines.append("")
    if items:
        for path in sorted(items):
            lines.append(f"- `{path}` (no vault graph node)")
    else:
        lines.append("None.")
    lines.append("")

    items = issues["manifest_issues"]
    lines.append(f"## Manifest Issues ({len(items)})")
    lines.append("")
    if items:
        for agent, link in items:
            lines.append(f"- `{agent}` manifest → `[[{link}]]` (no vault node)")
    else:
        lines.append("None.")
    lines.append("")

    items = issues["broken_canvas_links"]
    lines.append(f"## Broken Canvas Links ({len(items)})")
    lines.append("")
    if items:
        for canvas_path, name in items:
            lines.append(f"- `{canvas_path}` → `{name}` (no matching .md)")
    else:
        lines.append("None.")
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def send_summary(issues: dict) -> None:
    """Send Telegram summary if there are issues."""
    total = sum(len(v) for v in issues.values())
    if total == 0:
        log("No issues found — skipping Telegram")
        return

    today = date.today().isoformat()
    msg_parts = [f"📚 *Vault Audit — {today}*", f"Total issues: {total}", ""]

    if issues["missing_frontmatter"]:
        msg_parts.append(f"⚠️ Missing frontmatter: {len(issues['missing_frontmatter'])}")
    if issues["stale"]:
        msg_parts.append(f"🕐 Stale notes (>{STALE_DAYS}d): {len(issues['stale'])}")
    if issues["broken_wikilinks"]:
        msg_parts.append(f"🔗 Broken wikilinks: {len(issues['broken_wikilinks'])}")
    if issues["orphans"]:
        msg_parts.append(f"👻 Orphan notes: {len(issues['orphans'])}")

    if issues["broken_skill_sources"]:
        msg_parts.append(f"💀 Broken skill sources: {len(issues['broken_skill_sources'])}")
    if issues["orphaned_skills"]:
        msg_parts.append(f"📦 Orphaned shared skills: {len(issues['orphaned_skills'])}")
    if issues["manifest_issues"]:
        msg_parts.append(f"📋 Manifest issues: {len(issues['manifest_issues'])}")
    if issues["broken_canvas_links"]:
        msg_parts.append(f"🖼️ Broken canvas links: {len(issues['broken_canvas_links'])}")

    msg_parts.append("")
    msg_parts.append(f"Full report: `_librarian/reports/audit-{today}.md`")

    send_message("\n".join(msg_parts))


def cleanup_old_reports() -> None:
    """Remove audit reports older than REPORT_RETENTION_DAYS."""
    import time
    cutoff = time.time() - (REPORT_RETENTION_DAYS * 86400)
    removed = 0
    for f in REPORTS_DIR.glob("audit-*.md"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            removed += 1
    if removed:
        log(f"Cleaned up {removed} old report(s)")


def main() -> None:
    log("Starting vault audit")
    issues = run_audit()

    total = sum(len(v) for v in issues.values())
    log(f"Audit complete: {total} issue(s) found")

    report = write_report(issues)
    log(f"Report written: {report}")

    send_summary(issues)
    cleanup_old_reports()


if __name__ == "__main__":
    main()
