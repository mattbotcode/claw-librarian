#!/usr/bin/env python3
"""
session_reset.py — Flush agent session transcripts and reset session state.

Prevents token accumulation from long-running sessions by:
1. Archiving current session JSONL transcripts to a dated backup
2. Clearing the sessions.json mapping so the next interaction starts fresh
3. Archiving oversized cron/isolated sessions (>150KB) to prevent token buildup
4. Cleaning up stale .deleted transcript files older than 7 days

Designed to run via system cron every 6 hours.

Usage:
  python3 session_reset.py                  # Reset all agents
  python3 session_reset.py optic main       # Reset specific agents only
  python3 session_reset.py --dry-run        # Show what would be done without doing it
"""

import argparse
import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path

AGENTS_DIR = Path.home() / ".openclaw" / "agents"
ARCHIVE_DIR = Path.home() / ".openclaw" / "session-archive"

# Only reset persistent main sessions — cron sessions are already isolated
RESET_KEYS_PREFIX = [
    "agent:{agent}:main",  # The persistent interactive session
]

# Agents to reset by default
DEFAULT_AGENTS = ["main", "optic", "security", "analyst"]

# Cron/isolated session threshold — same as circuit_breaker.py
CRON_SIZE_THRESHOLD_KB = 150

# Stale .deleted file retention period
STALE_DAYS = 7


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def reset_agent(agent_id: str, dry_run: bool = False) -> dict:
    """Reset an agent's persistent session and clean up oversized cron sessions. Returns stats."""
    agent_dir = AGENTS_DIR / agent_id / "sessions"
    sessions_file = agent_dir / "sessions.json"

    if not sessions_file.exists():
        log(f"  {agent_id}: no sessions.json — skipping")
        return {"agent": agent_id, "status": "skipped", "reason": "no sessions.json"}

    with open(sessions_file) as f:
        sessions = json.load(f)

    if not sessions:
        log(f"  {agent_id}: no active sessions — skipping")
        return {"agent": agent_id, "status": "skipped", "reason": "empty"}

    today = datetime.now().strftime("%Y-%m-%d")
    archive_agent_dir = ARCHIVE_DIR / today / agent_id
    archived = []
    kept = []
    cron_archived = []

    # Identify which sessions to reset (persistent main sessions)
    # vs which to keep (cron run sessions — they're already isolated)
    sessions_to_remove = []
    for key, session_data in sessions.items():
        # Reset the main persistent session for this agent
        is_main = key == f"agent:{agent_id}:main"
        if is_main:
            session_id = session_data.get("sessionId", "unknown")
            transcript = agent_dir / f"{session_id}.jsonl"

            if transcript.exists():
                size_kb = transcript.stat().st_size // 1024

                if dry_run:
                    log(f"  {agent_id}: WOULD archive {key} ({size_kb}KB) → {archive_agent_dir}/")
                else:
                    archive_agent_dir.mkdir(parents=True, exist_ok=True)
                    archive_name = f"{session_id}_{today}.jsonl"
                    shutil.move(str(transcript), str(archive_agent_dir / archive_name))
                    log(f"  {agent_id}: archived {key} ({size_kb}KB)")

                archived.append({"key": key, "session_id": session_id, "size_kb": size_kb})
            else:
                log(f"  {agent_id}: {key} transcript not found — clearing mapping only")
                archived.append({"key": key, "session_id": session_id, "size_kb": 0})

            sessions_to_remove.append(key)
        else:
            kept.append(key)

    # --- Pass 2: Check non-main (cron/isolated) sessions for oversized transcripts ---
    for key in kept[:]:  # iterate a copy since we may modify `kept`
        session_data = sessions[key]
        session_id = session_data.get("sessionId", "unknown")
        transcript = agent_dir / f"{session_id}.jsonl"

        if not transcript.exists():
            continue

        size_kb = transcript.stat().st_size // 1024
        if size_kb > CRON_SIZE_THRESHOLD_KB:
            if dry_run:
                log(f"  {agent_id}: WOULD archive oversized cron session {key} ({size_kb}KB > {CRON_SIZE_THRESHOLD_KB}KB)")
            else:
                archive_agent_dir.mkdir(parents=True, exist_ok=True)
                archive_name = f"{session_id}_{today}.jsonl"
                shutil.move(str(transcript), str(archive_agent_dir / archive_name))
                log(f"  {agent_id}: archived oversized cron session {key} ({size_kb}KB)")

            cron_archived.append({"key": key, "session_id": session_id, "size_kb": size_kb})
            sessions_to_remove.append(key)
            kept.remove(key)

    # If nothing to remove at all (no main session AND no oversized cron sessions)
    if not sessions_to_remove:
        log(f"  {agent_id}: no sessions to reset")
        return {"agent": agent_id, "status": "skipped", "reason": "no sessions to reset"}

    # Write updated sessions.json without the reset sessions
    if not dry_run:
        updated = {k: v for k, v in sessions.items() if k not in sessions_to_remove}
        with open(sessions_file, "w") as f:
            json.dump(updated, f, indent=4)

    main_count = len(archived)
    cron_count = len(cron_archived)
    log(f"  {agent_id}: reset {main_count} main + {cron_count} oversized cron session(s), kept {len(kept)} cron session(s)")

    # --- Stale .deleted file cleanup ---
    stale_cleaned = cleanup_stale_files(agent_dir, dry_run)

    return {
        "agent": agent_id,
        "status": "reset",
        "archived": archived,
        "cron_archived": cron_archived,
        "kept": len(kept),
        "stale_cleaned": stale_cleaned,
    }


def cleanup_stale_files(agent_dir: Path, dry_run: bool = False) -> int:
    """Delete .deleted transcript files older than STALE_DAYS. Returns count of files removed."""
    if not agent_dir.exists():
        return 0

    cutoff = time.time() - (STALE_DAYS * 86400)
    cleaned = 0

    for f in agent_dir.iterdir():
        if not f.is_file():
            continue
        # Match files with .deleted in their name (e.g., abc123.jsonl.deleted, abc123.deleted.jsonl)
        if ".deleted" not in f.name:
            continue

        mtime = f.stat().st_mtime
        age_days = (time.time() - mtime) / 86400

        if mtime < cutoff:
            if dry_run:
                log(f"    WOULD delete stale file {f.name} ({age_days:.0f} days old)")
            else:
                f.unlink()
                log(f"    deleted stale file {f.name} ({age_days:.0f} days old)")
            cleaned += 1

    if cleaned > 0:
        log(f"    cleaned {cleaned} stale .deleted file(s)")

    return cleaned


# --- Self-healing error file rotation ---
ERROR_DIR = Path.home() / ".openclaw" / "errors"
ERROR_JSON_RETENTION_DAYS = 7
FIX_LOG_RETENTION_DAYS = 30


def cleanup_error_files(error_dir=None, dry_run: bool = False) -> int:
    """Rotate self-healing error JSONs (7d) and fix logs (30d). Returns count of files removed."""
    if error_dir is None:
        error_dir = ERROR_DIR
    if not error_dir.exists():
        return 0

    now = time.time()
    cleaned = 0

    for f in error_dir.iterdir():
        if not f.is_file():
            continue

        age_days = (now - f.stat().st_mtime) / 86400

        # Error JSONs and cooldown files: 7 day retention
        if f.name.endswith("_error.json") or f.name.endswith("_cooldown"):
            if age_days > ERROR_JSON_RETENTION_DAYS:
                if dry_run:
                    log(f"    WOULD delete error file {f.name} ({age_days:.0f} days old)")
                else:
                    f.unlink()
                    log(f"    deleted error file {f.name} ({age_days:.0f} days old)")
                cleaned += 1

        # Fix logs: 30 day retention (longer — learning data)
        elif f.name.endswith("_fixes.jsonl"):
            if age_days > FIX_LOG_RETENTION_DAYS:
                if dry_run:
                    log(f"    WOULD delete fix log {f.name} ({age_days:.0f} days old)")
                else:
                    f.unlink()
                    log(f"    deleted fix log {f.name} ({age_days:.0f} days old)")
                cleaned += 1

        # Diagnosis files: 7 day retention (same as errors)
        elif f.name.endswith("_diagnosis.md"):
            if age_days > ERROR_JSON_RETENTION_DAYS:
                if dry_run:
                    log(f"    WOULD delete diagnosis {f.name} ({age_days:.0f} days old)")
                else:
                    f.unlink()
                    log(f"    deleted diagnosis {f.name} ({age_days:.0f} days old)")
                cleaned += 1

    if cleaned > 0:
        log(f"    cleaned {cleaned} self-healing file(s)")

    return cleaned


def main():
    parser = argparse.ArgumentParser(description="Reset agent sessions to prevent token accumulation")
    parser.add_argument("agents", nargs="*", help="Agent IDs to reset (default: all active agents)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without doing it")
    args = parser.parse_args()

    agents = args.agents if args.agents else DEFAULT_AGENTS
    today = datetime.now().strftime("%Y-%m-%d")

    log(f"{'='*50}")
    log(f"  Session Reset — {today}")
    log(f"  Agents: {', '.join(agents)}")
    log(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    log(f"{'='*50}")

    results = []
    for agent_id in agents:
        if not (AGENTS_DIR / agent_id).exists():
            log(f"  {agent_id}: agent directory not found — skipping")
            continue
        result = reset_agent(agent_id, dry_run=args.dry_run)
        results.append(result)

    # --- Self-healing error file rotation ---
    log(f"  Rotating self-healing error files...")
    error_cleaned = cleanup_error_files(dry_run=args.dry_run)

    # Summary
    log(f"{'='*50}")
    reset_count = sum(1 for r in results if r["status"] == "reset")
    total_main_kb = sum(
        sum(a.get("size_kb", 0) for a in r.get("archived", []))
        for r in results
    )
    total_cron_kb = sum(
        sum(a.get("size_kb", 0) for a in r.get("cron_archived", []))
        for r in results
    )
    total_cron_count = sum(len(r.get("cron_archived", [])) for r in results)
    total_stale = sum(r.get("stale_cleaned", 0) for r in results)
    log(f"  {reset_count} agent(s) reset, {total_main_kb}KB main + {total_cron_kb}KB cron archived")
    if total_cron_count:
        log(f"  {total_cron_count} oversized cron session(s) cleaned up")
    if total_stale:
        log(f"  {total_stale} stale .deleted file(s) removed")
    if error_cleaned:
        log(f"  {error_cleaned} self-healing error file(s) rotated")
    if args.dry_run:
        log(f"  (dry run — no changes made)")
    log(f"{'='*50}")


if __name__ == "__main__":
    main()
