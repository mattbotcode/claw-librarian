# Claw-Librarian

**File-native memory coordination for multi-agent teams.**

Claw-Librarian is a sidecar memory manager for [OpenClaw](https://github.com/openclaw-ai) agents. Agents write structured events to a shared JSONL journal; the librarian indexes them into human-readable Markdown views and answers queries through a wikilink-aware graph search.

- **Zero external dependencies** — Python 3.11+ stdlib only
- **Event-sourced** — the JSONL journal is the single source of truth
- **Graph-aware** — queries expand through `[[wikilink]]` edges automatically
- **Concurrent-safe** — `fcntl` file locking prevents interleaved writes
- **Convention over configuration** — works out of the box, tune with `.claw-librarian.toml`

---

## Installation

```bash
git clone https://github.com/openclaw-ai/claw-librarian.git
cd claw-librarian
pip install -e .
```

The `claw` command is now available on your `$PATH`.

---

## Quick Start

### 1. Collect — record a journal entry

```bash
# Record a note from agent "optic" in project "macro-model"
claw collect "Ridge model retrained on 2025 data — R² improved to 0.83" \
    --agent optic \
    --project macro-model \
    --type milestone

# With a vault ref and tags
claw collect "Decided to drop momentum features below 3-month lookback" \
    --agent optic \
    --project macro-model \
    --type decision \
    --ref "projects/macro-model/lessons" \
    --tag feature-engineering

# From stdin (useful in pipelines)
echo "Cron job failed: FRED API timeout" | claw collect --agent kingpin --stdin
```

`collect` prints the ULID entry ID on stdout and returns immediately.

### 2. Index — build materialized views

```bash
# Incremental update (only new entries since last run)
claw index --vault ~/SystemVault

# Full rebuild
claw index --vault ~/SystemVault --full
```

Index writes two kinds of files into the vault:
- **`MAP.md`** — global index: active projects, recent events, agent activity table
- **`projects/<name>/context.md`** — per-project context window (last N entries, related nodes)

### 3. Query — search journal and vault

```bash
# Keyword search across journal and all vault Markdown files
claw query "momentum features" --vault ~/SystemVault

# Filter by project and agent
claw query "FRED" --project macro-model --agent optic

# Date range
claw query "rotation" --since 2026-01-01

# JSON output for scripting
claw query "Ridge" --format json | jq '.[].entry_id'

# Increase graph expansion depth (follow wikilinks 2 hops)
claw query "liquidity" --depth 2
```

**Output modes:**

| Mode | Flag | Use case |
|------|------|----------|
| Brief (default) | `--format brief` | Human-readable terminal output |
| JSON | `--format json` | Scripting, agent consumption |

---

## Architecture

```
Agents
  │
  ▼  claw collect
journal.jsonl  ◄──── single source of truth (append-only, locked)
  │
  ▼  claw index
MAP.md                          ← global vault index
projects/<name>/context.md      ← per-project context window
  │
  ▼  claw query
Query Engine
  ├── Phase 1a: keyword search over journal entries
  ├── Phase 1b: keyword grep over vault Markdown files
  └── Phase 2:  graph expansion via [[wikilink]] edges
        ├── forward refs (entry.refs → resolved vault paths)
        ├── outgoing wikilinks from vault hit files
        └── incoming backlinks to vault hit files
```

### Journal

Each call to `claw collect` appends one JSON line to `journal.jsonl`:

```json
{
  "schema_version": 1,
  "id": "01HZ...",
  "timestamp": "2026-03-15T10:23:44+00:00",
  "agent": "optic",
  "type": "milestone",
  "message": "Ridge model retrained — R² 0.83",
  "project": "macro-model",
  "refs": ["projects/macro-model/lessons"],
  "tags": ["training"],
  "metadata": {}
}
```

Valid `type` values: `milestone`, `discovery`, `decision`, `handoff`, `error`, `note`.

Writes are guarded by an exclusive `fcntl` lock on `.journal.lock`. Monthly rotation copies `journal.jsonl` to `journal-YYYY-MM.jsonl` (archive) and truncates the live file — coordinated through the same lock to prevent mid-rotation corruption.

### Materialized Views

`claw index` reads the journal and writes two kinds of Markdown files:

- **`MAP.md`** — global vault index: project list, recent events table, per-agent activity counts.
- **`projects/<name>/context.md`** — focused context window for a single project: recent entries (capped at `recent_events_cap`), related vault nodes (with TTL), and cross-references.

Views are rebuilt incrementally by default (tracking `last_indexed_id` in `.claw-librarian-state.json`). Pass `--full` for a clean rebuild.

### Graph-Aware Query

The query engine runs in two phases:

1. **Direct hits** — keyword match against journal entries (message + tags) and vault Markdown files (one hit per file).
2. **Graph expansion** — for each hit, follow outgoing `[[wikilinks]]` and incoming backlinks up to `depth` hops (default: 1). Related nodes are appended to results with a `link_density` score.

---

## Configuration

Claw-Librarian uses **convention over configuration**. All defaults work out of the box; override only what you need.

### Resolution Order

```
explicit overrides  (programmatic / adapter)
       ▲
 .claw-librarian.toml  (vault-root scoped)
       ▲
 adapter defaults      (e.g. OpenClaw preset)
       ▲
 built-in defaults
```

### `.claw-librarian.toml`

Place this file at the vault root. All keys are optional.

```toml
# Journal
journal_name = "journal.jsonl"       # JSONL file name
archive_dir  = "archive"             # Directory for rotated journals

# Index
map_name            = "MAP.md"       # Global index file name
state_name          = ".claw-librarian-state.json"
projects_dir_name   = "projects"     # Per-project context directory
context_file        = "context.md"   # Context file name inside each project dir
context_window_days = 30             # Days of history in context.md
recent_events_cap   = 50             # Max entries in context.md recent-events table
related_node_ttl_hours = 48          # TTL for ref-promoted related nodes

# Query
default_depth  = 1                   # Wikilink expansion hops
default_format = "brief"             # "brief" or "json"

# Agent
default_agent = ""                   # Used when --agent is omitted from CLI
```

Sections (`[vault]`, `[query]`, etc.) are flattened — you can group keys however you like, or use a flat file.

### Environment / CLI Override

Every command accepts `--vault <path>` to set the vault root without modifying config. Programmatic users can pass `overrides={}` to `load_config()`.

---

## OpenClaw Adapter

The `OpenClawAdapter` bridges the **SystemVault inbox protocol** into the journal. Agents drop `.md` files in `_inbox/` with YAML frontmatter; the adapter reads them, writes journal entries, and stamps each file with `journal_id` to prevent double-processing.

```python
from pathlib import Path
from claw_librarian.adapters.openclaw.adapter import OpenClawAdapter

adapter = OpenClawAdapter(vault_root=Path("~/SystemVault").expanduser())
entry_ids = adapter.bridge_inbox()
```

Agent names are discovered automatically from `team/*.md` files in the vault.

---

## Contributing

1. Fork the repo and create a branch: `git checkout -b feat/my-feature`
2. Write tests in `tests/` — run with `python -m pytest`
3. Keep the zero-dependency contract: **no third-party imports** in `claw_librarian/`
4. Open a pull request with a clear description of what changed and why

The test suite covers journal, config, graph, index, query, CLI, adapter, archiver, and a full integration scenario. Run the full suite:

```bash
python -m pytest -v
```

---

## License

MIT — see [LICENSE](LICENSE).

Copyright (c) 2026 Matthew & Contributors
