"""Generate per-project context.md from journal entries."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from claw_librarian.config import Config
from claw_librarian.journal.schema import JournalEntry


def build_context(
    project: str,
    entries: list[JournalEntry],
    config: Config,
    related_nodes: list[str] | None = None,
) -> str:
    """Build context.md content for a specific project."""
    today = date.today().isoformat()

    lines = [
        "---",
        f"title: {project} — Live Context",
        "type: context",
        f"updated: {today}",
        f"project: {project}",
        "generated_by: claw-librarian",
        "---",
        "",
        f"# {project} — Live Context",
        "",
    ]

    if not entries:
        lines.append("No activity recorded yet.")
        return "\n".join(lines)

    # Active Agents
    agent_last_seen: dict[str, str] = {}
    for entry in entries:
        if entry.agent not in agent_last_seen or entry.timestamp > agent_last_seen[entry.agent]:
            agent_last_seen[entry.agent] = entry.timestamp

    lines.append("## Active Agents")
    for agent, ts in sorted(agent_last_seen.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"- **{agent}** — last seen {ts[:16]}")
    lines.append("")

    # Group entries by date and type
    milestones: dict[str, list] = defaultdict(list)
    decisions: list = []
    handoffs: list = []
    errors: list = []

    for entry in sorted(entries, key=lambda e: e.timestamp, reverse=True):
        day = entry.timestamp[:10]
        ts_short = entry.timestamp[11:16] if len(entry.timestamp) > 16 else ""

        if entry.type in ("milestone", "discovery", "note"):
            milestones[day].append(f"- [{ts_short}] {entry.agent}: {entry.message}")
        elif entry.type == "decision":
            decisions.append(f"- [{day}] {entry.agent}: {entry.message}")
        elif entry.type == "handoff":
            handoffs.append(f"- [{day} {ts_short}] {entry.message}")
        elif entry.type == "error":
            errors.append(f"- [{day}] {entry.agent}: {entry.message}")

    # Recent Milestones
    lines.append("## Recent Milestones")
    for day in sorted(milestones.keys(), reverse=True):
        lines.append(f"### {day}")
        lines.extend(milestones[day])
    lines.append("")

    # Key Decisions
    if decisions:
        lines.append("## Key Decisions")
        lines.extend(decisions)
        lines.append("")

    # Related Nodes
    if related_nodes:
        lines.append("## Related Nodes")
        for node in related_nodes:
            lines.append(f"- [[{node}]]")
        lines.append("")

    # Handoffs
    if handoffs:
        lines.append("## Handoffs")
        lines.extend(handoffs)
        lines.append("")

    # Errors
    if errors:
        lines.append("## Errors")
        lines.extend(errors)
        lines.append("")

    return "\n".join(lines)
