# Claw-Librarian

**Your AI agents forget everything between sessions. This fixes that.**

Claw-Librarian gives multi-agent teams a shared memory. Agents write events to a local JSONL journal; the librarian indexes them into Markdown views your agents (and you) can actually read, and answers queries through a graph that follows `[[wikilinks]]` automatically.

No database. No server. No API keys. Just files.

```bash
# Agent finishes a task — record it
claw collect "Player dash hitbox tuned — movement feels tight now" \
    --agent kingpin --project my-game --type milestone

# Later, a different agent (or you) needs context
claw query "dash hitbox" --vault ~/my-vault
```

```
--- Direct Hits (2) ---
[2026-03-15T10:23] kingpin/my-game (01HZ...)
  Player dash hitbox tuned — movement feels tight now

projects/my-game/context.md:12
  Recent: Player dash hitbox tuned...

--- Related Nodes (3) ---
  [[projects/my-game/lessons]] — Game Dev Lessons
  [[projects/my-game/gdd]] — Game Design Document
  ...
```

The query didn't just find the journal entry — it followed the wikilink graph and surfaced the lessons file and design doc without being asked.

---

## Why?

Most agent memory solutions require a vector database, an embedding model, or a cloud service. Claw-Librarian takes a different approach:

- **Files are the database.** A single append-only JSONL file is the source of truth. You can `cat` it, `grep` it, `git diff` it, back it up with `cp`.
- **Markdown is the interface.** Materialized views (`MAP.md`, per-project `context.md`) are plain Markdown — readable by humans, agents, Obsidian, GitHub, anything.
- **Wikilinks are the graph.** No embeddings. No vector math. Your vault's `[[links]]` already encode what's related to what. The query engine just follows them.
- **Zero dependencies.** Python 3.11+ stdlib only. `pip install` and go. No Docker, no Redis, no pgvector.

If you run AI agents that work across sessions, across projects, or in teams — and you want them to remember what happened without bolting on infrastructure — this is for you.

---

## Installation

```bash
pip install git+https://github.com/mattbotcode/claw-librarian.git

# Or for development
git clone https://github.com/mattbotcode/claw-librarian.git
cd claw-librarian
pip install -e .
```

The `claw` CLI is now on your `$PATH`.

---

## Three Commands

### `claw collect` — record what happened

```bash
# Structured event from an agent
claw collect "Decided to drop momentum features below 3-month lookback" \
    --agent optic \
    --project macro-model \
    --type decision \
    --ref "projects/macro-model/lessons" \
    --tag feature-engineering

# Quick note
claw collect "FRED API timeout during overnight run" --agent kingpin --type error

# Pipe from scripts
echo "Deploy completed successfully" | claw collect --agent ci --stdin
```

Each call appends one JSON line to `journal.jsonl` and prints the entry's ULID on stdout. Writes are `fcntl`-locked — safe for concurrent agents.

### `claw index` — build the Markdown views

```bash
claw index --vault ~/my-vault          # incremental (fast)
claw index --vault ~/my-vault --full   # full rebuild
```

Produces:
- **`MAP.md`** — global index: active projects, recent events, agent activity
- **`projects/<name>/context.md`** — per-project context window with recent entries and related nodes

These files are designed to be dropped into an agent's context window at session start.

### `claw query` — search with graph expansion

```bash
claw query "momentum features" --vault ~/my-vault
claw query "FRED" --project macro-model --agent optic
claw query "liquidity" --depth 2        # follow wikilinks 2 hops
claw query "Ridge" --format json | jq . # JSON for scripting
```

The query engine searches the journal and vault Markdown files, then expands results through `[[wikilink]]` edges — surfacing related context you didn't explicitly search for.

---

## How It Works

```
Agents
  │
  ▼  claw collect
journal.jsonl  ◄──── append-only, fcntl-locked
  │
  ▼  claw index
MAP.md                        ← global vault overview
projects/<name>/context.md    ← per-project context window
  │
  ▼  claw query
Search + Graph Expansion
  ├── keyword match on journal + vault files
  └── 1-hop wikilink expansion (forward refs, outgoing links, backlinks)
```

### Journal Format

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

Event types: `milestone`, `discovery`, `decision`, `handoff`, `error`, `note`.

Monthly rotation archives old entries automatically (`journal-YYYY-MM.jsonl`).

### Graph-Aware Query

1. **Direct hits** — keyword match against journal entries and vault Markdown files
2. **Graph expansion** — for each hit, follow outgoing `[[wikilinks]]` and incoming backlinks up to N hops (default: 1). Related nodes get a `link_density` score so the most connected results surface first.

This means an agent searching for "authentication" will also find your security policy doc, the login flow design, and the session management notes — if they're linked in your vault.

---

## Configuration

Works out of the box. Override only what you need via `.claw-librarian.toml` at the vault root:

```toml
context_window_days = 30        # days of history in context.md
recent_events_cap   = 50        # max entries per context window
default_depth       = 1         # wikilink expansion hops
default_format      = "brief"   # "brief" or "json"
```

Full config reference: every key is optional, resolution order is `CLI overrides > .toml > adapter defaults > built-ins`.

---

## Adapters

Claw-Librarian has a generic core and pluggable adapters. The bundled **OpenClaw adapter** bridges the SystemVault inbox protocol — agents drop `.md` files with YAML frontmatter, the adapter writes journal entries and stamps files to prevent double-processing.

```python
from pathlib import Path
from claw_librarian.adapters.openclaw.adapter import OpenClawAdapter

adapter = OpenClawAdapter(vault_root=Path("~/my-vault").expanduser())
entry_ids = adapter.bridge_inbox()  # returns list of journal entry IDs
```

Writing your own adapter is straightforward — the core API is just `collect()`, `read_entries()`, `run_index()`, and `run_query()`.

---

## Contributing

1. Fork and branch: `git checkout -b feat/my-feature`
2. Write tests first — `python -m pytest -v` (109 tests across 9 test files)
3. **No third-party imports** in `claw_librarian/` — zero-dependency contract
4. Open a PR with a clear description

---

## License

MIT — see [LICENSE](LICENSE).

Copyright (c) 2026 Matthew & Contributors
