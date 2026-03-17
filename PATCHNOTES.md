# Patch Notes

## v0.2.0 — 2026-03-17

### Added

- **`scripts/`** — Operational scripts for SystemVault maintenance and agent session management:
  - `audit_vault.py` — Daily vault audit (frontmatter, wikilinks, staleness, orphans) with Telegram alerts
  - `process_inbox.py` — Inbox entry routing and merge processor (runs every 30 min via cron)
  - `sync_cc_memory.py` — Claude Code memory-to-vault sync (compares modification dates, writes inbox entries)
  - `extract_claude_sessions.py` — Extracts Claude Code session summaries from history for activity logs
  - `memory_compactor.py` — Graceful memory compaction for OpenClaw agents (80KB soft threshold with flush directive)
  - `session_reset.py` — Session transcript archival and reset (prevents token accumulation)
  - `validate_canvas.py` — Obsidian canvas validator (checks that agent nodes resolve to vault `.md` files)
  - `librarian_pipeline.sh` — Orchestrates inbox processing + `claw index` rebuild

- **`lib/`** — Shared utilities used by the operational scripts:
  - `frontmatter.py` — YAML frontmatter parse/serialize for SystemVault markdown files
  - `wikilinks.py` — Wikilink resolution, keyword search, backlink discovery
  - `telegram.py` — Telegram notification helper (reuses existing bot token)

### Fixed

- **`sys.path` resolution bug** in `sync_cc_memory.py`, `audit_vault.py`, and `process_inbox.py` — scripts used `Path(__file__).parent.parent` which produces a relative path when invoked from outside the script directory. Changed to `Path(__file__).resolve().parent.parent` so `lib/` imports work regardless of working directory.
