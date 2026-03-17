#!/usr/bin/env python3
"""
memory_compactor.py — Graceful memory compaction for OpenClaw agents.

Monitors agent transcript sizes and triggers structured memory flushes before
the circuit breaker's hard kill threshold (150KB). When a transcript exceeds
the configured threshold:

  1. Sends a flush directive via `openclaw agent --message`
  2. Agent writes a structured summary to memory/session_context.md
  3. Waits for confirmation (MEMORY_FLUSH_COMPLETE)
  4. Resets the session via session_reset.py (archives transcript, clears mapping)

Two-tier safety net:
   80KB → memory_compactor.py  (graceful flush + reset)
  150KB → circuit_breaker.py   (hard kill, existing fallback)

Designed to run via system cron every 20 minutes.

Usage:
  python3 memory_compactor.py              # Run checks and act
  python3 memory_compactor.py --dry-run    # Show what would happen without acting
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
AGENTS_DIR = Path.home() / ".openclaw" / "agents"
STATE_FILE = Path.home() / ".openclaw" / "scripts" / ".memory_compactor_state.json"
SESSION_RESET_SCRIPT = Path.home() / ".openclaw" / "scripts" / "session_reset.py"
CONFIG_FILE = Path.home() / ".openclaw" / "openclaw.json"

# Per-agent thresholds in KB. Add agents here when ready.
AGENT_THRESHOLDS = {
    "optic": 80,
}

# Agent workspace overrides (auto-detected from openclaw.json if possible)
AGENT_WORKSPACES = {
    "optic": "/home/mattbot/.openclaw/workspace-optic",
    "main": "/home/mattbot/.openclaw/workspace",
}

OPENCLAW_BIN = Path.home() / ".npm-global" / "bin" / "openclaw"

FLUSH_TIMEOUT = 90       # seconds to wait for agent to write memory
COOLDOWN_MINUTES = 30    # don't re-flush an agent within this window


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {}
    try:
        data = json.loads(STATE_FILE.read_text())
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_state(state: dict):
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception as e:
        log(f"  WARNING: failed to write state file: {e}")


def get_workspace(agent_id: str) -> str:
    """Get workspace path for an agent."""
    if agent_id in AGENT_WORKSPACES:
        return AGENT_WORKSPACES[agent_id]
    # Fallback: try to read from openclaw.json
    try:
        cfg = json.loads(CONFIG_FILE.read_text())
        for agent in cfg.get("agents", {}).get("list", []):
            if agent.get("id") == agent_id:
                ws = agent.get("workspace", "default")
                if ws != "default":
                    return ws
    except Exception:
        pass
    return str(Path.home() / ".openclaw" / f"workspace-{agent_id}")


# ---------------------------------------------------------------------------
# Transcript size detection
# ---------------------------------------------------------------------------
def get_transcript_size(agent_id: str) -> tuple[float, str | None]:
    """
    Find the active main transcript for an agent.
    Returns (size_kb, transcript_path) or (0, None) if not found.
    """
    sessions_file = AGENTS_DIR / agent_id / "sessions" / "sessions.json"
    if not sessions_file.exists():
        return 0, None

    try:
        sessions = json.loads(sessions_file.read_text())
    except (json.JSONDecodeError, OSError):
        return 0, None

    main_key = f"agent:{agent_id}:main"
    session_data = sessions.get(main_key)
    if not session_data:
        return 0, None

    session_id = session_data.get("sessionId")
    if not session_id:
        return 0, None

    transcript = AGENTS_DIR / agent_id / "sessions" / f"{session_id}.jsonl"
    if not transcript.exists():
        return 0, None

    try:
        size_kb = transcript.stat().st_size / 1024
        return size_kb, str(transcript)
    except OSError:
        return 0, None


# ---------------------------------------------------------------------------
# Flush directive
# ---------------------------------------------------------------------------
def build_flush_message(size_kb: float, workspace: str) -> str:
    """Build the structured flush directive message."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""SYSTEM DIRECTIVE — MEMORY COMPACTION

Your transcript has reached {size_kb:.0f}KB. Flush your memory now.

Write a structured summary to {workspace}/memory/session_context.md with these sections:

## Active Session Context (flushed {ts})

### Conversation Summary
- Who you were talking to and what they asked (bullet per topic)
- What you answered or delivered
- For any images received: describe the content in 1-2 sentences (do NOT reference raw media file paths)

### Work Products
- Files created or modified (full paths)
- Current state (completed/in-progress/blocked)

### Active Files
- Scripts, configs, outputs relevant to resuming work

### Pending / Last Topic
- What was the last thing discussed
- Any unanswered questions or next steps

Reply MEMORY_FLUSH_COMPLETE when done."""


def send_flush_directive(agent_id: str, size_kb: float, workspace: str) -> bool:
    """
    Send the flush directive via openclaw agent CLI.
    Returns True if agent confirmed MEMORY_FLUSH_COMPLETE.
    """
    message = build_flush_message(size_kb, workspace)

    cmd = [
        str(OPENCLAW_BIN), "agent",
        "--agent", agent_id,
        "--message", message,
        "--timeout", str(FLUSH_TIMEOUT),
        "--json",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=FLUSH_TIMEOUT + 30,  # extra buffer beyond openclaw's own timeout
        )

        if result.returncode != 0:
            log(f"    openclaw agent failed (code {result.returncode}): {result.stderr[:200]}")
            return False

        # Parse JSON response
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            log(f"    Failed to parse openclaw response: {result.stdout[:200]}")
            return False

        status = data.get("status")
        if status != "ok":
            log(f"    openclaw agent status: {status}")
            return False

        # Extract reply text
        payloads = data.get("result", {}).get("payloads", [])
        reply_text = ""
        for p in payloads:
            text = p.get("text", "")
            if text:
                reply_text += text

        if "MEMORY_FLUSH_COMPLETE" in reply_text:
            log(f"    Agent confirmed flush complete")
            return True
        else:
            log(f"    Agent did not confirm flush. Reply: {reply_text[:200]}")
            return False

    except subprocess.TimeoutExpired:
        log(f"    Flush directive timed out after {FLUSH_TIMEOUT + 30}s")
        return False
    except Exception as e:
        log(f"    Flush directive error: {e}")
        return False


# ---------------------------------------------------------------------------
# Session reset
# ---------------------------------------------------------------------------
def reset_agent_session(agent_id: str) -> bool:
    """Reset the agent's session via session_reset.py. Returns True on success."""
    try:
        result = subprocess.run(
            [sys.executable, str(SESSION_RESET_SCRIPT), agent_id],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            log(f"    Session reset complete")
            return True
        else:
            log(f"    Session reset failed (code {result.returncode}): {result.stderr[:200]}")
            return False
    except Exception as e:
        log(f"    Session reset error: {e}")
        return False


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------
def check_agent(agent_id: str, threshold_kb: int, state: dict, dry_run: bool) -> bool:
    """
    Check one agent's transcript size. If over threshold and cooldown expired,
    trigger a graceful flush + reset.
    Returns True if a flush was triggered (or would be in dry-run).
    """
    size_kb, _transcript_path = get_transcript_size(agent_id)

    if size_kb == 0:
        log(f"  {agent_id}: no active transcript")
        return False

    log(f"  {agent_id}: transcript {size_kb:.0f}KB (threshold {threshold_kb}KB)")

    if size_kb < threshold_kb:
        return False

    # Check cooldown
    agent_state = state.get(agent_id, {})
    last_flush = agent_state.get("last_flush_ts")
    if last_flush:
        try:
            last_dt = datetime.fromisoformat(last_flush)
            cooldown_until = last_dt + timedelta(minutes=COOLDOWN_MINUTES)
            if datetime.now() < cooldown_until:
                remaining = (cooldown_until - datetime.now()).total_seconds() / 60
                log(f"  {agent_id}: SKIP — cooldown active ({remaining:.0f}min remaining)")
                return False
        except (ValueError, TypeError):
            pass  # invalid timestamp, proceed with flush

    # --- THRESHOLD EXCEEDED, COOLDOWN CLEAR ---
    log(f"  {agent_id}: FLUSH TRIGGERED ({size_kb:.0f}KB >= {threshold_kb}KB)")

    workspace = get_workspace(agent_id)

    if dry_run:
        log(f"  {agent_id}: DRY RUN — would send flush directive and reset session")
        return True

    # Step 1: Send flush directive
    log(f"    Sending flush directive...")
    flush_ok = send_flush_directive(agent_id, size_kb, workspace)

    if not flush_ok:
        log(f"    FLUSH FAILED — leaving session intact for circuit_breaker.py fallback")
        # Update state so we don't spam retries every 20 min
        agent_state["last_flush_ts"] = datetime.now().isoformat()
        agent_state["last_flush_status"] = "failed"
        state[agent_id] = agent_state
        return False

    # Step 2: Reset session (archives transcript, clears mapping)
    log(f"    Resetting session...")
    reset_ok = reset_agent_session(agent_id)

    # Update state
    agent_state["last_flush_ts"] = datetime.now().isoformat()
    agent_state["last_flush_size_kb"] = round(size_kb, 1)
    agent_state["last_flush_status"] = "ok" if reset_ok else "flush_ok_reset_failed"
    agent_state["flush_count"] = agent_state.get("flush_count", 0) + 1
    state[agent_id] = agent_state

    if reset_ok:
        log(f"  {agent_id}: COMPACTION COMPLETE — flushed {size_kb:.0f}KB, session reset")
    else:
        log(f"  {agent_id}: WARNING — memory flushed but session reset failed")

    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Graceful memory compaction for OpenClaw agents"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would happen without taking any action"
    )
    args = parser.parse_args()

    log("=" * 55)
    log(f"  Memory Compactor — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    log(f"  Agents: {', '.join(f'{a} ({t}KB)' for a, t in AGENT_THRESHOLDS.items())}")
    log(f"  Cooldown: {COOLDOWN_MINUTES}min")
    log("=" * 55)

    state = load_state()
    flushed = []

    for agent_id, threshold_kb in AGENT_THRESHOLDS.items():
        triggered = check_agent(agent_id, threshold_kb, state, args.dry_run)
        if triggered:
            flushed.append(agent_id)

    save_state(state)

    # Summary
    log("=" * 55)
    if flushed:
        action = "would flush" if args.dry_run else "flushed"
        log(f"  {len(flushed)} agent(s) {action}: {', '.join(flushed)}")
    else:
        log(f"  All clear — no agents exceeded thresholds")
    if args.dry_run:
        log(f"  (dry run — no changes made)")
    log("=" * 55)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL: unhandled exception: {e}")
        sys.exit(1)
