# Claw-Librarian Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a file-native memory coordination CLI for multi-agent teams — JSONL journal as source of truth, Markdown materialized views, graph-aware search.

**Architecture:** Event-sourced system with three CLI commands (`collect`, `index`, `query`). Generic Python core with zero external deps. OpenClaw adapter for SystemVault integration. Extracted from existing `_librarian/` code where applicable.

**Tech Stack:** Python 3.11+ (stdlib only), JSONL, Markdown, YAML frontmatter, wikilinks, argparse CLI

**Spec:** `~/SystemVault/projects/claw-librarian/spec.md`

**Approach:** TDD — every feature gets a failing test first, then implementation, then green. Security review before PR.

---

## File Map

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Package metadata, `[project.scripts]` entry point for `claw` CLI |
| `claw_librarian/__init__.py` | Package version |
| `claw_librarian/config.py` | Load `.claw-librarian.toml`, merge defaults, resolve paths |
| `claw_librarian/journal/_ulid.py` | Minimal ULID generator (48-bit timestamp + 80-bit random) |
| `claw_librarian/journal/schema.py` | `JournalEntry` dataclass, validation, serialization |
| `claw_librarian/journal/writer.py` | Locked append to JSONL |
| `claw_librarian/journal/reader.py` | Stream/filter/query entries from JSONL files |
| `claw_librarian/journal/rotation.py` | Monthly rotation + summary generation |
| `claw_librarian/graph/frontmatter.py` | Parse/serialize YAML frontmatter (extracted from `_librarian/`) |
| `claw_librarian/graph/wikilinks.py` | Extract, resolve, traverse wikilinks (extracted from `_librarian/`) |
| `claw_librarian/graph/backlinks.py` | Build reverse link index from vault files |
| `claw_librarian/index/indexer.py` | Main incremental loop: journal → views |
| `claw_librarian/index/map_builder.py` | Generate MAP.md |
| `claw_librarian/index/context_builder.py` | Generate per-project context.md |
| `claw_librarian/index/archiver.py` | Monthly snapshot + archive + re-hydration |
| `claw_librarian/query/engine.py` | Search journal + vault, rank by freshness |
| `claw_librarian/query/expander.py` | 1-hop graph expansion (forward + backward) |
| `claw_librarian/adapters/openclaw/adapter.py` | Inbox bridge, agent identity, config preset |
| `claw_librarian/adapters/openclaw/defaults.toml` | OpenClaw config preset |
| `claw_librarian/cli/main.py` | argparse CLI: `claw collect\|index\|query` |
| `tests/conftest.py` | Temp vault fixtures, journal helpers |
| `tests/test_journal.py` | ULID, schema, writer, reader tests |
| `tests/test_graph.py` | Frontmatter, wikilinks, backlinks tests |
| `tests/test_index.py` | Indexer, map builder, context builder tests |
| `tests/test_archiver.py` | Rotation, archival, re-hydration tests |
| `tests/test_query.py` | Search, expansion, ranking tests |
| `tests/test_cli.py` | CLI integration tests (subprocess calls) |
| `tests/test_adapter.py` | OpenClaw adapter + inbox bridge tests |
| `tests/test_config.py` | Config loading + TOML override tests |
| `tests/test_integration.py` | Full round-trip collect → index → query |

---

## Chunk 1: Project Scaffold + Journal Core

### Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `claw_librarian/__init__.py`
- Create: `claw_librarian/journal/__init__.py`
- Create: `claw_librarian/graph/__init__.py`
- Create: `claw_librarian/index/__init__.py`
- Create: `claw_librarian/query/__init__.py`
- Create: `claw_librarian/adapters/__init__.py`
- Create: `claw_librarian/adapters/openclaw/__init__.py`
- Create: `claw_librarian/cli/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `LICENSE`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "claw-librarian"
version = "0.1.0"
description = "File-native memory coordination for multi-agent teams"
readme = "README.md"
license = "MIT"
requires-python = ">=3.11"
authors = [
    {name = "Matthew"},
    {name = "Kingpin", email = "kingpin@openclaw.ai"},
]

[project.scripts]
claw = "claw_librarian.cli.main:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create all `__init__.py` files**

`claw_librarian/__init__.py`:
```python
"""Claw-Librarian: File-native memory coordination for multi-agent teams."""

__version__ = "0.1.0"
```

All other `__init__.py` files are empty.

- [ ] **Step 3: Create `tests/conftest.py` with vault fixtures**

```python
"""Shared test fixtures for claw-librarian."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest


@pytest.fixture
def tmp_vault(tmp_path):
    """Create a temporary vault directory with standard structure."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "projects").mkdir()
    (vault / "projects" / "test-project").mkdir()
    (vault / "team").mkdir()
    return vault


@pytest.fixture
def tmp_journal(tmp_vault):
    """Return the path to a journal.jsonl in the temp vault."""
    return tmp_vault / "journal.jsonl"


@pytest.fixture
def sample_entry():
    """Return a valid journal entry dict."""
    return {
        "schema_version": 1,
        "id": "01JQXK7V3M9N2P4R5T6W8Y0Z",
        "timestamp": "2026-03-15T14:32:07.123000Z",
        "agent": "cipher",
        "project": "test-project",
        "type": "milestone",
        "message": "Completed auth test suite",
        "refs": ["projects/test-project/api-spec"],
        "tags": ["testing"],
        "metadata": {},
    }


@pytest.fixture
def populated_journal(tmp_journal, sample_entry):
    """Create a journal with several entries."""
    entries = []
    for i, (agent, typ, msg) in enumerate([
        ("cipher", "milestone", "Completed auth test suite"),
        ("atlas", "handoff", "Passing API work to cipher"),
        ("cipher", "decision", "Using Ridge over Lasso"),
        ("optic", "milestone", "Updated CPI chart"),
    ]):
        entry = sample_entry.copy()
        entry["id"] = f"01JQXK7V3M9N2P4R5T6W{i:04d}"
        entry["agent"] = agent
        entry["type"] = typ
        entry["message"] = msg
        if agent == "optic":
            entry["project"] = "macro-charts"
        entries.append(entry)
    with open(tmp_journal, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return tmp_journal


@pytest.fixture
def vault_with_files(tmp_vault):
    """Create a vault with markdown files containing wikilinks."""
    # Project file
    spec = tmp_vault / "projects" / "test-project" / "api-spec.md"
    spec.write_text(
        "---\ntitle: API Spec\nkeywords: [api, spec]\nstatus: active\n"
        "type: spec\nupdated: 2026-03-15\n---\n\n"
        "# API Spec\n\nSee [[tests]] and [[lessons]].\n"
    )
    tests = tmp_vault / "projects" / "test-project" / "tests.md"
    tests.write_text(
        "---\ntitle: Tests\nkeywords: [tests]\nstatus: active\n"
        "type: project\nupdated: 2026-03-15\n---\n\n"
        "# Tests\n\nCovers [[api-spec]] endpoints.\n"
    )
    lessons = tmp_vault / "projects" / "test-project" / "lessons.md"
    lessons.write_text(
        "---\ntitle: Lessons\nkeywords: [lessons]\nstatus: active\n"
        "type: lesson\nupdated: 2026-03-14\n---\n\n"
        "# Lessons\n\nAuth tokens must be refreshed before retry.\n"
    )
    # Team file
    cipher = tmp_vault / "team" / "cipher.md"
    cipher.write_text(
        "---\ntitle: Cipher\nkeywords: [cipher, agent]\nstatus: active\n"
        "type: agent\nupdated: 2026-03-15\n---\n\n# Cipher\n"
    )
    return tmp_vault
```

- [ ] **Step 4: Create MIT LICENSE**

- [ ] **Step 5: Verify scaffold**

Run: `cd ~/claw-librarian && python -m pytest tests/ -v --co`
Expected: collected 0 items (no tests yet, but no import errors)

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "chore: project scaffold with package structure and test fixtures"
```

---

### Task 2: ULID Generator

**Files:**
- Create: `claw_librarian/journal/_ulid.py`
- Test: `tests/test_journal.py`

- [ ] **Step 1: Write failing tests for ULID**

In `tests/test_journal.py`:
```python
"""Tests for journal module: ULID, schema, writer, reader."""

import time

from claw_librarian.journal._ulid import generate_ulid


class TestULID:
    def test_ulid_is_26_chars(self):
        uid = generate_ulid()
        assert len(uid) == 26

    def test_ulid_uses_crockford_base32(self):
        uid = generate_ulid()
        valid_chars = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
        assert all(c in valid_chars for c in uid)

    def test_ulid_is_sortable_by_time(self):
        uid1 = generate_ulid()
        time.sleep(0.002)  # 2ms gap
        uid2 = generate_ulid()
        assert uid2 > uid1

    def test_ulid_uniqueness(self):
        ids = {generate_ulid() for _ in range(1000)}
        assert len(ids) == 1000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/claw-librarian && python -m pytest tests/test_journal.py::TestULID -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement ULID generator**

`claw_librarian/journal/_ulid.py`:
```python
"""Minimal ULID generator — no external dependencies.

ULID = 48-bit ms timestamp (Crockford Base32) + 80-bit random.
Total: 26 characters, lexicographically sortable by time.
"""

import os
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_ulid() -> str:
    """Generate a new ULID string."""
    # Timestamp: milliseconds since Unix epoch, 10 chars
    ts_ms = int(time.time() * 1000)
    ts_chars = []
    for _ in range(10):
        ts_chars.append(_CROCKFORD[ts_ms & 0x1F])
        ts_ms >>= 5
    ts_part = "".join(reversed(ts_chars))

    # Randomness: 80 bits = 10 bytes, 16 chars
    rand_bytes = os.urandom(10)
    rand_val = int.from_bytes(rand_bytes, "big")
    rand_chars = []
    for _ in range(16):
        rand_chars.append(_CROCKFORD[rand_val & 0x1F])
        rand_val >>= 5
    rand_part = "".join(reversed(rand_chars))

    return ts_part + rand_part
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claw-librarian && python -m pytest tests/test_journal.py::TestULID -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add claw_librarian/journal/_ulid.py tests/test_journal.py
git commit -m "feat: minimal ULID generator with no external deps"
```

---

### Task 3: Journal Schema

**Files:**
- Create: `claw_librarian/journal/schema.py`
- Test: `tests/test_journal.py` (append to)

- [ ] **Step 1: Write failing tests for schema**

Append to `tests/test_journal.py`:
```python
import json
import pytest
from claw_librarian.journal.schema import JournalEntry, validate_entry, VALID_TYPES


class TestJournalSchema:
    def test_create_entry(self, sample_entry):
        entry = JournalEntry(**sample_entry)
        assert entry.agent == "cipher"
        assert entry.schema_version == 1

    def test_entry_to_json_line(self, sample_entry):
        entry = JournalEntry(**sample_entry)
        line = entry.to_json_line()
        parsed = json.loads(line)
        assert parsed["agent"] == "cipher"
        assert not line.endswith("\n")

    def test_entry_from_json_line(self, sample_entry):
        line = json.dumps(sample_entry)
        entry = JournalEntry.from_json_line(line)
        assert entry.agent == "cipher"
        assert entry.project == "test-project"

    def test_validate_valid_entry(self, sample_entry):
        errors = validate_entry(sample_entry)
        assert errors == []

    def test_validate_missing_required(self):
        errors = validate_entry({"schema_version": 1})
        assert len(errors) > 0
        assert any("agent" in e for e in errors)

    def test_validate_invalid_type(self, sample_entry):
        sample_entry["type"] = "invalid_type"
        errors = validate_entry(sample_entry)
        assert any("type" in e for e in errors)

    def test_valid_types(self):
        assert "milestone" in VALID_TYPES
        assert "handoff" in VALID_TYPES
        assert "note" in VALID_TYPES

    def test_optional_fields_default_to_none_or_empty(self):
        minimal = {
            "schema_version": 1,
            "id": "01TEST",
            "timestamp": "2026-03-15T00:00:00Z",
            "agent": "test",
            "type": "note",
            "message": "hello",
        }
        entry = JournalEntry(**minimal)
        assert entry.project is None
        assert entry.refs == []
        assert entry.tags == []
        assert entry.metadata == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/claw-librarian && python -m pytest tests/test_journal.py::TestJournalSchema -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement schema**

`claw_librarian/journal/schema.py`:
```python
"""Journal entry schema — dataclass, validation, serialization."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict

VALID_TYPES = frozenset({
    "milestone", "discovery", "decision", "handoff", "error", "note",
})

REQUIRED_FIELDS = {"schema_version", "id", "timestamp", "agent", "type", "message"}


@dataclass
class JournalEntry:
    """A single journal event."""

    schema_version: int
    id: str
    timestamp: str
    agent: str
    type: str
    message: str
    project: str | None = None
    refs: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_json_line(self) -> str:
        """Serialize to a single JSON line (no trailing newline)."""
        d = asdict(self)
        # Omit None project for cleaner output
        if d["project"] is None:
            d["project"] = None
        return json.dumps(d, ensure_ascii=False)

    @classmethod
    def from_json_line(cls, line: str) -> JournalEntry:
        """Deserialize from a JSON line."""
        d = json.loads(line)
        return cls(
            schema_version=d["schema_version"],
            id=d["id"],
            timestamp=d["timestamp"],
            agent=d["agent"],
            type=d["type"],
            message=d["message"],
            project=d.get("project"),
            refs=d.get("refs", []),
            tags=d.get("tags", []),
            metadata=d.get("metadata", {}),
        )


def validate_entry(data: dict) -> list[str]:
    """Validate a raw dict against the journal schema. Returns list of error strings."""
    errors = []
    for f in REQUIRED_FIELDS:
        if f not in data:
            errors.append(f"missing required field: {f}")
    if "type" in data and data["type"] not in VALID_TYPES:
        errors.append(f"invalid type: {data['type']} (valid: {', '.join(sorted(VALID_TYPES))})")
    if "schema_version" in data and data["schema_version"] != 1:
        errors.append(f"unsupported schema_version: {data['schema_version']}")
    return errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claw-librarian && python -m pytest tests/test_journal.py::TestJournalSchema -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add claw_librarian/journal/schema.py tests/test_journal.py
git commit -m "feat: journal entry schema with validation and serialization"
```

---

### Task 4: Journal Writer (with file locking)

**Files:**
- Create: `claw_librarian/journal/writer.py`
- Test: `tests/test_journal.py` (append to)

- [ ] **Step 1: Write failing tests for writer**

Append to `tests/test_journal.py`:
```python
from claw_librarian.journal.writer import collect
from claw_librarian.journal.schema import JournalEntry


class TestJournalWriter:
    def test_collect_creates_journal_file(self, tmp_journal):
        entry_id = collect(
            journal_path=tmp_journal,
            agent="cipher",
            message="Test message",
        )
        assert tmp_journal.exists()
        assert len(entry_id) == 26  # ULID

    def test_collect_appends_valid_json(self, tmp_journal):
        collect(journal_path=tmp_journal, agent="cipher", message="First")
        collect(journal_path=tmp_journal, agent="atlas", message="Second")
        lines = tmp_journal.read_text().strip().split("\n")
        assert len(lines) == 2
        entry1 = json.loads(lines[0])
        entry2 = json.loads(lines[1])
        assert entry1["agent"] == "cipher"
        assert entry2["agent"] == "atlas"

    def test_collect_with_all_fields(self, tmp_journal):
        collect(
            journal_path=tmp_journal,
            agent="cipher",
            message="Full entry",
            project="test-project",
            entry_type="milestone",
            refs=["projects/test-project/api-spec"],
            tags=["auth"],
            metadata={"key": "value"},
        )
        line = tmp_journal.read_text().strip()
        entry = json.loads(line)
        assert entry["project"] == "test-project"
        assert entry["type"] == "milestone"
        assert entry["refs"] == ["projects/test-project/api-spec"]
        assert entry["tags"] == ["auth"]
        assert entry["metadata"] == {"key": "value"}

    def test_collect_default_type_is_note(self, tmp_journal):
        collect(journal_path=tmp_journal, agent="test", message="No type")
        entry = json.loads(tmp_journal.read_text().strip())
        assert entry["type"] == "note"

    def test_collect_returns_ulid(self, tmp_journal):
        entry_id = collect(journal_path=tmp_journal, agent="test", message="Hi")
        assert len(entry_id) == 26

    def test_newlines_in_message_dont_break_jsonl(self, tmp_journal):
        """Embedded newlines must not split a JSONL line."""
        collect(journal_path=tmp_journal, agent="test", message="Line1\nLine2\nLine3")
        lines = tmp_journal.read_text().strip().split("\n")
        assert len(lines) == 1  # Still one JSONL line
        entry = json.loads(lines[0])
        assert "Line1\nLine2" in entry["message"]

    def test_concurrent_writes_no_corruption(self, tmp_journal):
        """Simulate rapid sequential writes (true concurrency tested in integration)."""
        for i in range(50):
            collect(journal_path=tmp_journal, agent=f"agent-{i}", message=f"Msg {i}")
        lines = tmp_journal.read_text().strip().split("\n")
        assert len(lines) == 50
        for line in lines:
            json.loads(line)  # Should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/claw-librarian && python -m pytest tests/test_journal.py::TestJournalWriter -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement writer with file locking**

`claw_librarian/journal/writer.py`:
```python
"""Journal writer — locked append to JSONL."""

from __future__ import annotations

import fcntl
import json
from datetime import datetime, timezone
from pathlib import Path

from ._ulid import generate_ulid
from .schema import JournalEntry


def collect(
    journal_path: Path,
    agent: str,
    message: str,
    project: str | None = None,
    entry_type: str = "note",
    refs: list[str] | None = None,
    tags: list[str] | None = None,
    metadata: dict | None = None,
) -> str:
    """Append a journal entry. Returns the entry ID (ULID).

    Acquires an exclusive lock on .journal.lock (shared with rotation)
    to prevent interleaved writes and mid-rotation corruption.
    """
    entry_id = generate_ulid()
    timestamp = datetime.now(timezone.utc).isoformat()

    entry = JournalEntry(
        schema_version=1,
        id=entry_id,
        timestamp=timestamp,
        agent=agent,
        type=entry_type,
        message=message,
        project=project,
        refs=refs or [],
        tags=tags or [],
        metadata=metadata or {},
    )

    line = entry.to_json_line() + "\n"

    # Ensure parent directory exists
    journal_path.parent.mkdir(parents=True, exist_ok=True)

    lock_path = journal_path.parent / ".journal.lock"
    lock_path.touch(exist_ok=True)
    with open(lock_path, "r") as lock_fd:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        try:
            with open(journal_path, "a", encoding="utf-8") as f:
                f.write(line)
                f.flush()
        finally:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)

    return entry_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claw-librarian && python -m pytest tests/test_journal.py::TestJournalWriter -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add claw_librarian/journal/writer.py tests/test_journal.py
git commit -m "feat: journal writer with fcntl file locking for atomic appends"
```

---

### Task 5: Journal Reader

**Files:**
- Create: `claw_librarian/journal/reader.py`
- Test: `tests/test_journal.py` (append to)

- [ ] **Step 1: Write failing tests for reader**

Append to `tests/test_journal.py`:
```python
from claw_librarian.journal.reader import (
    read_entries,
    read_entries_since,
    filter_entries,
)


class TestJournalReader:
    def test_read_all_entries(self, populated_journal):
        entries = list(read_entries(populated_journal))
        assert len(entries) == 4

    def test_read_empty_journal(self, tmp_journal):
        tmp_journal.touch()
        entries = list(read_entries(tmp_journal))
        assert entries == []

    def test_read_nonexistent_journal(self, tmp_vault):
        entries = list(read_entries(tmp_vault / "nope.jsonl"))
        assert entries == []

    def test_read_entries_since_id(self, populated_journal):
        all_entries = list(read_entries(populated_journal))
        since_id = all_entries[1].id  # skip first 2
        entries = list(read_entries_since(populated_journal, since_id))
        assert len(entries) == 2

    def test_read_skips_malformed_lines(self, tmp_journal):
        tmp_journal.write_text(
            '{"schema_version":1,"id":"A","timestamp":"T","agent":"a","type":"note","message":"ok"}\n'
            'NOT JSON\n'
            '{"schema_version":1,"id":"B","timestamp":"T","agent":"b","type":"note","message":"ok"}\n'
        )
        entries = list(read_entries(tmp_journal))
        assert len(entries) == 2
        assert entries[0].id == "A"
        assert entries[1].id == "B"

    def test_filter_by_project(self, populated_journal):
        entries = list(filter_entries(
            read_entries(populated_journal),
            project="macro-charts",
        ))
        assert len(entries) == 1
        assert entries[0].agent == "optic"

    def test_filter_by_agent(self, populated_journal):
        entries = list(filter_entries(
            read_entries(populated_journal),
            agent="cipher",
        ))
        assert len(entries) == 2

    def test_filter_by_type(self, populated_journal):
        entries = list(filter_entries(
            read_entries(populated_journal),
            entry_type="milestone",
        ))
        assert len(entries) == 2

    def test_filter_by_since_date(self, populated_journal):
        # All sample entries have same timestamp, so filtering by date won't exclude
        entries = list(filter_entries(
            read_entries(populated_journal),
            since="2026-03-14",
        ))
        assert len(entries) == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/claw-librarian && python -m pytest tests/test_journal.py::TestJournalReader -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: Implement reader**

`claw_librarian/journal/reader.py`:
```python
"""Journal reader — stream, filter, and query JSONL entries."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path

from .schema import JournalEntry


def read_entries(journal_path: Path) -> Iterator[JournalEntry]:
    """Stream all valid entries from a journal file. Skips malformed lines."""
    if not journal_path.exists():
        return
    with open(journal_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = JournalEntry.from_json_line(line)
                yield entry
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                print(
                    f"warning: skipping malformed line {line_num} in "
                    f"{journal_path.name}: {e}",
                    file=sys.stderr,
                )


def read_entries_since(
    journal_path: Path, since_id: str
) -> Iterator[JournalEntry]:
    """Yield entries that come AFTER the given ID (exclusive)."""
    found = False
    for entry in read_entries(journal_path):
        if found:
            yield entry
        elif entry.id == since_id:
            found = True


def filter_entries(
    entries: Iterator[JournalEntry],
    *,
    project: str | None = None,
    agent: str | None = None,
    entry_type: str | None = None,
    since: str | None = None,
) -> Iterator[JournalEntry]:
    """Filter an entry stream by project, agent, type, or date."""
    for entry in entries:
        if project and entry.project != project:
            continue
        if agent and entry.agent != agent:
            continue
        if entry_type and entry.type != entry_type:
            continue
        if since and entry.timestamp < since:
            continue
        yield entry
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claw-librarian && python -m pytest tests/test_journal.py::TestJournalReader -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add claw_librarian/journal/reader.py tests/test_journal.py
git commit -m "feat: journal reader with streaming, filtering, and malformed line resilience"
```

---

### Task 6: Config loader

**Files:**
- Create: `claw_librarian/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_config.py`:
```python
"""Tests for config loading."""

from pathlib import Path

from claw_librarian.config import load_config, Config, DEFAULTS


class TestConfig:
    def test_defaults_without_toml(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault)
        assert cfg.vault_root == tmp_vault
        assert cfg.journal_name == "journal.jsonl"
        assert cfg.map_name == "MAP.md"
        assert cfg.context_window_days == 30
        assert cfg.related_node_ttl_hours == 48

    def test_journal_path(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault)
        assert cfg.journal_path == tmp_vault / "journal.jsonl"

    def test_toml_override(self, tmp_vault):
        toml_file = tmp_vault / ".claw-librarian.toml"
        toml_file.write_text(
            '[rotation]\ncontext_window_days = 14\n'
        )
        cfg = load_config(vault_root=tmp_vault)
        assert cfg.context_window_days == 14

    def test_cli_override(self, tmp_vault):
        cfg = load_config(
            vault_root=tmp_vault,
            overrides={"default_agent": "cipher"},
        )
        assert cfg.default_agent == "cipher"

    def test_state_path(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault)
        assert cfg.state_path == tmp_vault / ".claw-librarian-state.json"

    def test_projects_dir(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault)
        assert cfg.projects_dir == tmp_vault / "projects"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/claw-librarian && python -m pytest tests/test_config.py -v`
Expected: FAIL

- [ ] **Step 3: Implement config**

`claw_librarian/config.py`:
```python
"""Configuration — convention defaults + .claw-librarian.toml override."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULTS = {
    "journal_name": "journal.jsonl",
    "map_name": "MAP.md",
    "state_name": ".claw-librarian-state.json",
    "projects_dir_name": "projects",
    "context_file": "context.md",
    "archive_dir": "archive",
    "context_window_days": 30,
    "related_node_ttl_hours": 48,
    "default_depth": 1,
    "default_format": "brief",
    "default_agent": "",
    "recent_events_cap": 50,
}


@dataclass
class Config:
    """Resolved configuration."""

    vault_root: Path
    journal_name: str
    map_name: str
    state_name: str
    projects_dir_name: str
    context_file: str
    archive_dir: str
    context_window_days: int
    related_node_ttl_hours: int
    default_depth: int
    default_format: str
    default_agent: str
    recent_events_cap: int

    @property
    def journal_path(self) -> Path:
        return self.vault_root / self.journal_name

    @property
    def map_path(self) -> Path:
        return self.vault_root / self.map_name

    @property
    def state_path(self) -> Path:
        return self.vault_root / self.state_name

    @property
    def projects_dir(self) -> Path:
        return self.vault_root / self.projects_dir_name


def _load_toml(vault_root: Path) -> dict:
    """Load .claw-librarian.toml if it exists. Flattens sections."""
    toml_path = vault_root / ".claw-librarian.toml"
    if not toml_path.exists():
        return {}
    with open(toml_path, "rb") as f:
        raw = tomllib.load(f)
    # Flatten: top-level scalar keys stay as-is, section dicts get merged
    flat = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            flat.update(value)
        else:
            flat[key] = value
    return flat


def load_config(
    vault_root: Path,
    adapter_defaults: dict | None = None,
    overrides: dict | None = None,
) -> Config:
    """Load config with resolution order: overrides > toml > adapter > defaults."""
    merged = dict(DEFAULTS)
    if adapter_defaults:
        merged.update(adapter_defaults)
    merged.update(_load_toml(vault_root))
    if overrides:
        merged.update(overrides)
    return Config(vault_root=vault_root, **{
        k: merged[k] for k in DEFAULTS
    })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claw-librarian && python -m pytest tests/test_config.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add claw_librarian/config.py tests/test_config.py
git commit -m "feat: config loader with convention defaults and TOML override"
```

---

## Chunk 2: Graph Module (Extracted from _librarian/)

### Task 7: Frontmatter parser

**Files:**
- Create: `claw_librarian/graph/frontmatter.py`
- Test: `tests/test_graph.py`

Source reference: `~/SystemVault/_librarian/scripts/lib/frontmatter.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_graph.py`:
```python
"""Tests for graph module: frontmatter, wikilinks, backlinks."""

from pathlib import Path

from claw_librarian.graph.frontmatter import parse, parse_file, serialize


class TestFrontmatter:
    def test_parse_with_frontmatter(self):
        text = "---\ntitle: Hello\nstatus: active\n---\n\n# Body\n"
        meta, body = parse(text)
        assert meta["title"] == "Hello"
        assert "# Body" in body

    def test_parse_without_frontmatter(self):
        text = "# Just a heading\n\nSome text.\n"
        meta, body = parse(text)
        assert meta is None
        assert body == text

    def test_parse_yaml_list(self):
        text = "---\nkeywords: [a, b, c]\n---\n\nBody\n"
        meta, body = parse(text)
        assert meta["keywords"] == ["a", "b", "c"]

    def test_parse_quoted_strings(self):
        text = '---\ntitle: "Quoted Title"\n---\n\nBody\n'
        meta, body = parse(text)
        assert meta["title"] == "Quoted Title"

    def test_serialize_roundtrip(self):
        meta = {"title": "Test", "keywords": ["a", "b"], "status": "active"}
        body = "# Content\n"
        output = serialize(meta, body)
        meta2, body2 = parse(output)
        assert meta2["title"] == "Test"
        assert meta2["keywords"] == ["a", "b"]
        assert "# Content" in body2

    def test_parse_file(self, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("---\ntitle: File\n---\n\nContent\n")
        meta, body = parse_file(f)
        assert meta["title"] == "File"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/claw-librarian && python -m pytest tests/test_graph.py::TestFrontmatter -v`
Expected: FAIL

- [ ] **Step 3: Implement frontmatter (extract from `_librarian/`)**

`claw_librarian/graph/frontmatter.py` — adapted from existing `lib/frontmatter.py`:

```python
"""YAML frontmatter parse/write utilities for Markdown files."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path


def parse(text: str) -> tuple[dict | None, str]:
    """Parse YAML frontmatter from markdown text.

    Returns (metadata_dict, body) or (None, full_text) if no frontmatter.
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not match:
        return None, text

    raw_yaml = match.group(1)
    body = match.group(2)

    meta: dict = {}
    for line in raw_yaml.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value.startswith("[") and value.endswith("]"):
            value = [
                v.strip().strip('"').strip("'")
                for v in value[1:-1].split(",")
                if v.strip()
            ]
        elif value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        meta[key] = value

    return meta, body


def parse_file(path: Path) -> tuple[dict | None, str]:
    """Parse frontmatter from a file path."""
    text = path.read_text(encoding="utf-8")
    return parse(text)


def serialize(meta: dict, body: str) -> str:
    """Serialize metadata dict + body back to frontmatter markdown."""
    lines = ["---"]
    for key, value in meta.items():
        if isinstance(value, list):
            lines.append(f"{key}: [{', '.join(str(v) for v in value)}]")
        elif isinstance(value, date):
            lines.append(f"{key}: {value.isoformat()}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    body = body.lstrip("\n")
    lines.append(body)
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claw-librarian && python -m pytest tests/test_graph.py::TestFrontmatter -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add claw_librarian/graph/frontmatter.py tests/test_graph.py
git commit -m "feat: frontmatter parser extracted from _librarian with serialize support"
```

---

### Task 8: Wikilinks resolver

**Files:**
- Create: `claw_librarian/graph/wikilinks.py`
- Test: `tests/test_graph.py` (append to)

Source reference: `~/SystemVault/_librarian/scripts/lib/wikilinks.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_graph.py`:
```python
from claw_librarian.graph.wikilinks import (
    extract_wikilinks,
    resolve_ref,
    find_all_vault_files,
)


class TestWikilinks:
    def test_extract_simple(self):
        links = extract_wikilinks("See [[target]] for details.")
        assert links == ["target"]

    def test_extract_with_display(self):
        links = extract_wikilinks("See [[target|display text]].")
        assert links == ["target"]

    def test_extract_with_section(self):
        links = extract_wikilinks("See [[target#section]].")
        assert links == ["target"]

    def test_extract_multiple(self):
        links = extract_wikilinks("[[a]] and [[b]] and [[c]]")
        assert links == ["a", "b", "c"]

    def test_extract_none(self):
        links = extract_wikilinks("No links here.")
        assert links == []

    def test_resolve_ref_literal_path(self, vault_with_files):
        result = resolve_ref("projects/test-project/api-spec", vault_with_files)
        assert result is not None
        assert result.name == "api-spec.md"

    def test_resolve_ref_stem_fallback(self, vault_with_files):
        result = resolve_ref("api-spec", vault_with_files)
        assert result is not None
        assert result.name == "api-spec.md"

    def test_resolve_ref_not_found(self, vault_with_files):
        result = resolve_ref("nonexistent", vault_with_files)
        assert result is None

    def test_find_all_vault_files(self, vault_with_files):
        files = find_all_vault_files(vault_with_files)
        names = {f.name for f in files}
        assert "api-spec.md" in names
        assert "tests.md" in names

    def test_find_excludes_internal_dirs(self, vault_with_files):
        internal = vault_with_files / "_inbox"
        internal.mkdir()
        (internal / "temp.md").write_text("temp")
        files = find_all_vault_files(vault_with_files)
        names = {f.name for f in files}
        assert "temp.md" not in names
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/claw-librarian && python -m pytest tests/test_graph.py::TestWikilinks -v`
Expected: FAIL

- [ ] **Step 3: Implement wikilinks**

`claw_librarian/graph/wikilinks.py`:
```python
"""Wikilink extraction and resolution for Markdown vaults."""

from __future__ import annotations

import re
from pathlib import Path

EXCLUDE_DIRS = {"_inbox", "_librarian", "_templates", ".obsidian", "_processed", "_review"}


def find_all_vault_files(vault_root: Path) -> list[Path]:
    """Return all .md files in the vault, excluding internal dirs."""
    results = []
    for path in vault_root.rglob("*.md"):
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        results.append(path)
    return results


def extract_wikilinks(text: str) -> list[str]:
    """Extract all [[wikilink]] targets from text.

    Handles [[target]], [[target|display]], and [[target#section]] forms.
    """
    raw = re.findall(r"\[\[([^\]]+)\]\]", text)
    results = []
    for m in raw:
        target = re.split(r"\\?\|", m)[0]
        target = target.split("#")[0].strip()
        if target:
            results.append(target)
    return results


def resolve_ref(ref: str, vault_root: Path, vault_files: list[Path] | None = None) -> Path | None:
    """Resolve a ref to a vault file.

    Resolution order:
    1. Literal vault-relative path: {vault_root}/{ref}.md
    2. Stem-only match (case-insensitive) for Obsidian compatibility
    """
    # Try literal path first
    literal = vault_root / f"{ref}.md"
    if literal.exists():
        return literal

    # Fall back to stem matching
    if vault_files is None:
        vault_files = find_all_vault_files(vault_root)
    ref_stem = ref.lower().strip()
    # If ref has slashes, use just the last segment as stem
    if "/" in ref_stem:
        ref_stem = ref_stem.rsplit("/", 1)[-1]
    for f in vault_files:
        if f.stem.lower() == ref_stem:
            return f
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claw-librarian && python -m pytest tests/test_graph.py::TestWikilinks -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add claw_librarian/graph/wikilinks.py tests/test_graph.py
git commit -m "feat: wikilink extraction and dual-resolution (path + stem fallback)"
```

---

### Task 9: Backlinks index

**Files:**
- Create: `claw_librarian/graph/backlinks.py`
- Test: `tests/test_graph.py` (append to)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_graph.py`:
```python
from claw_librarian.graph.backlinks import build_backlink_index, incoming_links


class TestBacklinks:
    def test_build_index(self, vault_with_files):
        index = build_backlink_index(vault_with_files)
        # api-spec links to tests and lessons
        # tests links to api-spec
        assert len(index) > 0

    def test_incoming_links(self, vault_with_files):
        target = vault_with_files / "projects" / "test-project" / "api-spec.md"
        sources = incoming_links(target, vault_with_files)
        source_names = {s.name for s in sources}
        assert "tests.md" in source_names  # tests.md links to [[api-spec]]

    def test_no_self_links(self, vault_with_files):
        target = vault_with_files / "projects" / "test-project" / "api-spec.md"
        sources = incoming_links(target, vault_with_files)
        assert target not in sources

    def test_incoming_links_nonexistent(self, vault_with_files):
        target = vault_with_files / "nope.md"
        sources = incoming_links(target, vault_with_files)
        assert sources == []
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/claw-librarian && python -m pytest tests/test_graph.py::TestBacklinks -v`
Expected: FAIL

- [ ] **Step 3: Implement backlinks**

`claw_librarian/graph/backlinks.py`:
```python
"""Reverse link index — find all files that link TO a given target."""

from __future__ import annotations

from pathlib import Path

from .wikilinks import find_all_vault_files, extract_wikilinks, resolve_ref


def build_backlink_index(vault_root: Path) -> dict[Path, list[Path]]:
    """Build a map of target -> [source files that link to it]."""
    vault_files = find_all_vault_files(vault_root)
    index: dict[Path, list[Path]] = {}

    for source in vault_files:
        try:
            text = source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        links = extract_wikilinks(text)
        for link in links:
            target = resolve_ref(link, vault_root, vault_files)
            if target and target != source:
                index.setdefault(target, []).append(source)

    return index


def incoming_links(
    target: Path,
    vault_root: Path,
    vault_files: list[Path] | None = None,
) -> list[Path]:
    """Find all vault files that link TO the given target."""
    if vault_files is None:
        vault_files = find_all_vault_files(vault_root)

    if not target.exists():
        return []

    target_stem = target.stem.lower()
    sources = []
    for f in vault_files:
        if f == target:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        links = extract_wikilinks(text)
        for link in links:
            link_stem = link.lower().strip()
            if "/" in link_stem:
                link_stem = link_stem.rsplit("/", 1)[-1]
            if link_stem == target_stem:
                sources.append(f)
                break
    return sources
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claw-librarian && python -m pytest tests/test_graph.py::TestBacklinks -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add claw_librarian/graph/backlinks.py tests/test_graph.py
git commit -m "feat: backlink index for reverse wikilink traversal"
```

---

## Chunk 3: Indexer (MAP.md + context.md)

### Task 10: Map builder

**Files:**
- Create: `claw_librarian/index/map_builder.py`
- Test: `tests/test_index.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_index.py`:
```python
"""Tests for index module: map builder, context builder, indexer."""

import json
from datetime import datetime, timezone

from claw_librarian.config import load_config
from claw_librarian.journal.schema import JournalEntry
from claw_librarian.index.map_builder import build_map


class TestMapBuilder:
    def _make_entries(self):
        return [
            JournalEntry(
                schema_version=1, id="01A", timestamp="2026-03-15T14:32:00Z",
                agent="cipher", project="test-project", type="milestone",
                message="Completed auth tests",
            ),
            JournalEntry(
                schema_version=1, id="01B", timestamp="2026-03-15T12:00:00Z",
                agent="optic", project="macro-charts", type="milestone",
                message="Updated CPI chart",
            ),
            JournalEntry(
                schema_version=1, id="01C", timestamp="2026-03-15T09:00:00Z",
                agent="atlas", project="test-project", type="handoff",
                message="Passing API work to cipher",
            ),
        ]

    def test_build_map_contains_projects(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault)
        content = build_map(self._make_entries(), cfg)
        assert "test-project" in content
        assert "macro-charts" in content

    def test_build_map_contains_agents(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault)
        content = build_map(self._make_entries(), cfg)
        assert "cipher" in content
        assert "optic" in content

    def test_build_map_contains_recent_events(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault)
        content = build_map(self._make_entries(), cfg)
        assert "Completed auth tests" in content

    def test_build_map_header(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault)
        content = build_map(self._make_entries(), cfg)
        assert "# Vault Map" in content
        assert "Auto-generated by claw-librarian" in content

    def test_build_map_caps_recent_events(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault, overrides={"recent_events_cap": 2})
        entries = self._make_entries()
        content = build_map(entries, cfg)
        # Only 2 most recent should appear in recent events
        lines = [l for l in content.split("\n") if l.startswith("- **")]
        assert len(lines) <= 2

    def test_build_map_empty_entries(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault)
        content = build_map([], cfg)
        assert "# Vault Map" in content
        assert "No active projects" in content or "Active Projects" in content
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/claw-librarian && python -m pytest tests/test_index.py::TestMapBuilder -v`
Expected: FAIL

- [ ] **Step 3: Implement map builder**

`claw_librarian/index/map_builder.py`:
```python
"""Generate MAP.md — the global vault index."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from claw_librarian.config import Config
from claw_librarian.journal.schema import JournalEntry


def build_map(entries: list[JournalEntry], config: Config) -> str:
    """Build MAP.md content from journal entries."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Vault Map",
        f"> Auto-generated by claw-librarian. Last sync: {now}",
        "",
    ]

    if not entries:
        lines.append("## Active Projects")
        lines.append("")
        lines.append("No active projects.")
        lines.append("")
        lines.append("## Agent Status")
        lines.append("")
        lines.append("No agents seen.")
        return "\n".join(lines)

    # Aggregate per-project info
    project_data: dict[str, dict] = defaultdict(lambda: {
        "last_ts": "", "agents": set(), "last_activity": "",
    })
    agent_data: dict[str, dict] = defaultdict(lambda: {
        "last_ts": "", "project": "",
    })

    for entry in entries:
        proj = entry.project or "(cross-project)"
        pd = project_data[proj]
        if entry.timestamp > pd["last_ts"]:
            pd["last_ts"] = entry.timestamp
            pd["last_activity"] = entry.timestamp
        pd["agents"].add(entry.agent)

        ad = agent_data[entry.agent]
        if entry.timestamp > ad["last_ts"]:
            ad["last_ts"] = entry.timestamp
            ad["project"] = proj

    # Active Projects table
    lines.append("## Active Projects")
    lines.append("")
    lines.append("| Project | Last Activity | Active Agents | Link |")
    lines.append("|---------|--------------|---------------|------|")
    for proj, pd in sorted(project_data.items(), key=lambda x: x[1]["last_ts"], reverse=True):
        agents_str = ", ".join(sorted(pd["agents"]))
        ts = _format_time(pd["last_ts"])
        link = f"[[projects/{proj}/context]]" if proj != "(cross-project)" else ""
        lines.append(f"| {proj} | {ts} | {agents_str} | {link} |")
    lines.append("")

    # Recent Events (capped)
    lines.append("## Recent Events (last 24h)")
    lines.append("")
    recent = sorted(entries, key=lambda e: e.timestamp, reverse=True)
    cap = config.recent_events_cap
    for entry in recent[:cap]:
        ts_short = entry.timestamp[11:16] if len(entry.timestamp) > 16 else entry.timestamp
        proj = entry.project or "cross"
        lines.append(f"- **{ts_short}** {entry.agent}/{proj}: {entry.message}")
    lines.append("")

    # Agent Status table
    lines.append("## Agent Status")
    lines.append("")
    lines.append("| Agent | Last Seen | Current Project |")
    lines.append("|-------|-----------|----------------|")
    for agent, ad in sorted(agent_data.items(), key=lambda x: x[1]["last_ts"], reverse=True):
        ts = _format_time(ad["last_ts"])
        lines.append(f"| {agent} | {ts} | {ad['project']} |")
    lines.append("")

    return "\n".join(lines)


def _format_time(iso_ts: str) -> str:
    """Format ISO timestamp as relative or absolute time string."""
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - dt
        if delta.total_seconds() < 3600:
            mins = int(delta.total_seconds() / 60)
            return f"{mins} min ago"
        elif delta.total_seconds() < 86400:
            hours = int(delta.total_seconds() / 3600)
            return f"{hours} hours ago"
        else:
            days = delta.days
            return f"{days} day{'s' if days != 1 else ''} ago"
    except (ValueError, TypeError):
        return iso_ts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claw-librarian && python -m pytest tests/test_index.py::TestMapBuilder -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add claw_librarian/index/map_builder.py tests/test_index.py
git commit -m "feat: MAP.md builder with project/agent tables and capped recent events"
```

---

### Task 11: Context builder

**Files:**
- Create: `claw_librarian/index/context_builder.py`
- Test: `tests/test_index.py` (append to)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_index.py`:
```python
from claw_librarian.index.context_builder import build_context


class TestContextBuilder:
    def _project_entries(self):
        return [
            JournalEntry(
                schema_version=1, id="01A", timestamp="2026-03-15T14:32:00Z",
                agent="cipher", project="test-project", type="milestone",
                message="Completed auth tests",
                refs=["projects/test-project/api-spec"],
            ),
            JournalEntry(
                schema_version=1, id="01B", timestamp="2026-03-15T09:00:00Z",
                agent="atlas", project="test-project", type="handoff",
                message="Passing API work to cipher",
            ),
            JournalEntry(
                schema_version=1, id="01C", timestamp="2026-03-14T16:00:00Z",
                agent="cipher", project="test-project", type="decision",
                message="Using Ridge over Lasso",
            ),
        ]

    def test_context_has_frontmatter(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault)
        content = build_context("test-project", self._project_entries(), cfg)
        assert "---" in content
        assert "test-project" in content
        assert "generated_by: claw-librarian" in content

    def test_context_has_agents(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault)
        content = build_context("test-project", self._project_entries(), cfg)
        assert "cipher" in content
        assert "atlas" in content

    def test_context_has_milestones(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault)
        content = build_context("test-project", self._project_entries(), cfg)
        assert "Completed auth tests" in content

    def test_context_has_decisions(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault)
        content = build_context("test-project", self._project_entries(), cfg)
        assert "Using Ridge over Lasso" in content

    def test_context_has_handoffs(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault)
        content = build_context("test-project", self._project_entries(), cfg)
        assert "Passing API work to cipher" in content

    def test_context_has_related_nodes(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault)
        content = build_context(
            "test-project", self._project_entries(), cfg,
            related_nodes=["projects/test-project/api-spec"],
        )
        assert "[[projects/test-project/api-spec]]" in content

    def test_context_empty_entries(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault)
        content = build_context("test-project", [], cfg)
        assert "test-project" in content
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/claw-librarian && python -m pytest tests/test_index.py::TestContextBuilder -v`
Expected: FAIL

- [ ] **Step 3: Implement context builder**

`claw_librarian/index/context_builder.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claw-librarian && python -m pytest tests/test_index.py::TestContextBuilder -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add claw_librarian/index/context_builder.py tests/test_index.py
git commit -m "feat: per-project context.md builder with milestones, decisions, handoffs"
```

---

### Task 12: Indexer main loop

**Files:**
- Create: `claw_librarian/index/indexer.py`
- Test: `tests/test_index.py` (append to)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_index.py`:
```python
from claw_librarian.index.indexer import run_index, load_state, save_state


class TestIndexer:
    def test_run_index_creates_map(self, tmp_vault, populated_journal):
        cfg = load_config(vault_root=tmp_vault)
        run_index(cfg)
        map_path = tmp_vault / "MAP.md"
        assert map_path.exists()
        content = map_path.read_text()
        assert "# Vault Map" in content

    def test_run_index_creates_context(self, tmp_vault, populated_journal):
        cfg = load_config(vault_root=tmp_vault)
        (tmp_vault / "projects" / "macro-charts").mkdir(parents=True, exist_ok=True)
        run_index(cfg)
        ctx = tmp_vault / "projects" / "test-project" / "context.md"
        assert ctx.exists()
        content = ctx.read_text()
        assert "cipher" in content

    def test_run_index_updates_state(self, tmp_vault, populated_journal):
        cfg = load_config(vault_root=tmp_vault)
        run_index(cfg)
        state = load_state(cfg.state_path)
        assert state["last_indexed_id"] != ""
        assert state["schema_version"] == 1

    def test_run_index_incremental(self, tmp_vault, populated_journal):
        cfg = load_config(vault_root=tmp_vault)
        run_index(cfg)
        state1 = load_state(cfg.state_path)
        # Run again with no new entries
        run_index(cfg)
        state2 = load_state(cfg.state_path)
        assert state2["last_indexed_id"] == state1["last_indexed_id"]

    def test_load_state_default(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault)
        state = load_state(cfg.state_path)
        assert state["schema_version"] == 1
        assert state["last_indexed_id"] == ""

    def test_run_index_full_rebuild(self, tmp_vault, populated_journal):
        cfg = load_config(vault_root=tmp_vault)
        run_index(cfg)
        run_index(cfg, full=True)
        map_path = tmp_vault / "MAP.md"
        assert map_path.exists()
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/claw-librarian && python -m pytest tests/test_index.py::TestIndexer -v`
Expected: FAIL

- [ ] **Step 3: Implement indexer**

`claw_librarian/index/indexer.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claw-librarian && python -m pytest tests/test_index.py::TestIndexer -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add claw_librarian/index/indexer.py tests/test_index.py
git commit -m "feat: incremental indexer with state tracking and related node TTL"
```

---

## Chunk 4: Archiver + Rotation

### Task 13: Archiver and journal rotation

**Files:**
- Create: `claw_librarian/index/archiver.py`
- Create: `claw_librarian/journal/rotation.py`
- Test: `tests/test_archiver.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_archiver.py`:
```python
"""Tests for archiver and journal rotation."""

import json
from datetime import date
from pathlib import Path

from claw_librarian.config import load_config
from claw_librarian.journal.rotation import rotate_journal, needs_rotation, _previous_month
from claw_librarian.index.archiver import archive_context, rehydrate_context
from claw_librarian.index.indexer import load_state, save_state


class TestRotation:
    def test_needs_rotation_first_run(self):
        assert needs_rotation("") is True

    def test_needs_rotation_same_month(self):
        current = date.today().strftime("%Y-%m")
        assert needs_rotation(current) is False

    def test_needs_rotation_old_month(self):
        assert needs_rotation("2025-01") is True

    def test_rotate_journal(self, tmp_vault, populated_journal):
        cfg = load_config(vault_root=tmp_vault)
        state = {"last_rotation": "2025-01"}
        rotate_journal(cfg, state)
        # Old journal should be archived with PREVIOUS month label
        prev = _previous_month()
        archived = list(tmp_vault.glob("journal-*.jsonl"))
        assert len(archived) == 1
        assert prev in archived[0].name
        # Current journal should be empty (truncated)
        assert cfg.journal_path.exists()
        assert cfg.journal_path.stat().st_size == 0
        # State should be updated
        assert state["last_rotation"] == date.today().strftime("%Y-%m")

    def test_rotate_journal_skips_if_current(self, tmp_vault, populated_journal):
        cfg = load_config(vault_root=tmp_vault)
        state = {"last_rotation": date.today().strftime("%Y-%m")}
        rotate_journal(cfg, state)
        archived = list(tmp_vault.glob("journal-*.jsonl"))
        assert len(archived) == 0


class TestArchiver:
    def test_archive_context(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault)
        ctx_path = tmp_vault / "projects" / "test-project" / "context.md"
        ctx_path.write_text("# Context\n\nSome content.\n")
        archive_context("test-project", cfg, "2026-03")
        archive_path = tmp_vault / "projects" / "test-project" / "archive" / "context-2026-03.md"
        assert archive_path.exists()
        assert "Some content" in archive_path.read_text()

    def test_rehydrate_context(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault)
        # Create an archived context
        archive_dir = tmp_vault / "projects" / "test-project" / "archive"
        archive_dir.mkdir(parents=True)
        (archive_dir / "context-2026-02.md").write_text("# Old Context\n")
        result = rehydrate_context("test-project", cfg)
        assert result is not None
        assert "Old Context" in result

    def test_rehydrate_no_archive(self, tmp_vault):
        cfg = load_config(vault_root=tmp_vault)
        result = rehydrate_context("nonexistent-project", cfg)
        assert result is None
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/claw-librarian && python -m pytest tests/test_archiver.py -v`
Expected: FAIL

- [ ] **Step 3: Implement rotation**

`claw_librarian/journal/rotation.py`:
```python
"""Journal rotation — monthly rename + summary generation."""

from __future__ import annotations

import fcntl
import shutil
from datetime import date, timedelta
from pathlib import Path

from claw_librarian.config import Config


def needs_rotation(last_rotation: str) -> bool:
    """Check if journal needs rotation based on last rotation month."""
    current_month = date.today().strftime("%Y-%m")
    return last_rotation != current_month


def _previous_month() -> str:
    """Get YYYY-MM for the previous month (the month being archived)."""
    first_of_month = date.today().replace(day=1)
    last_of_prev = first_of_month - timedelta(days=1)
    return last_of_prev.strftime("%Y-%m")


def rotate_journal(config: Config, state: dict) -> None:
    """Rotate journal.jsonl to journal-YYYY-MM.jsonl if needed.

    Uses a lock file to coordinate with concurrent writers. The
    sequence is:
    1. Acquire exclusive lock on .journal.lock
    2. Copy journal.jsonl → journal-YYYY-MM.jsonl (previous month)
    3. Truncate journal.jsonl to empty
    4. Release lock
    This avoids the rename-while-locked pitfall (fcntl locks are
    bound to fd, not path).
    """
    if not needs_rotation(state.get("last_rotation", "")):
        return

    journal = config.journal_path
    if not journal.exists() or journal.stat().st_size == 0:
        state["last_rotation"] = date.today().strftime("%Y-%m")
        return

    prev_month = _previous_month()
    archive_name = f"journal-{prev_month}.jsonl"
    archive_path = journal.parent / archive_name
    lock_path = journal.parent / ".journal.lock"

    # Lock, copy, truncate, unlock
    lock_path.touch()
    with open(lock_path, "r") as lock_fd:
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
        try:
            shutil.copy2(journal, archive_path)
            journal.write_text("")
        finally:
            fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)

    state["last_rotation"] = date.today().strftime("%Y-%m")
```

- [ ] **Step 4: Implement archiver**

`claw_librarian/index/archiver.py`:
```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ~/claw-librarian && python -m pytest tests/test_archiver.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add claw_librarian/journal/rotation.py claw_librarian/index/archiver.py tests/test_archiver.py
git commit -m "feat: journal rotation with file locking and context archival/rehydration"
```

---

## Chunk 5: Query Engine

### Task 14: Query engine (search + rank)

**Files:**
- Create: `claw_librarian/query/engine.py`
- Test: `tests/test_query.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_query.py`:
```python
"""Tests for query engine and graph expander."""

import json

from claw_librarian.config import load_config
from claw_librarian.query.engine import search, SearchResult


class TestQueryEngine:
    def test_search_journal_hits(self, tmp_vault, populated_journal):
        cfg = load_config(vault_root=tmp_vault)
        results = search("auth", cfg)
        direct = [r for r in results if r.source_type == "journal"]
        assert len(direct) >= 1
        assert any("auth" in r.message.lower() for r in direct)

    def test_search_vault_hits(self, vault_with_files):
        cfg = load_config(vault_root=vault_with_files)
        # Create a journal so search doesn't fail
        (vault_with_files / "journal.jsonl").touch()
        results = search("auth tokens", cfg)
        vault_hits = [r for r in results if r.source_type == "vault"]
        assert len(vault_hits) >= 1

    def test_search_no_results(self, tmp_vault, populated_journal):
        cfg = load_config(vault_root=tmp_vault)
        results = search("xyznonexistent", cfg)
        assert results == []

    def test_search_scoped_by_project(self, tmp_vault, populated_journal):
        cfg = load_config(vault_root=tmp_vault)
        results = search("auth", cfg, project="macro-charts")
        for r in results:
            if r.source_type == "journal":
                assert r.project == "macro-charts" or r.project is None

    def test_search_scoped_by_agent(self, tmp_vault, populated_journal):
        cfg = load_config(vault_root=tmp_vault)
        results = search("Completed", cfg, agent="cipher")
        journal_hits = [r for r in results if r.source_type == "journal"]
        for r in journal_hits:
            assert r.agent == "cipher"

    def test_results_sorted_by_freshness(self, tmp_vault, populated_journal):
        cfg = load_config(vault_root=tmp_vault)
        results = search("", cfg)  # match all
        journal_hits = [r for r in results if r.source_type == "journal"]
        if len(journal_hits) > 1:
            timestamps = [r.timestamp for r in journal_hits]
            assert timestamps == sorted(timestamps, reverse=True)

    def test_search_result_fields(self, tmp_vault, populated_journal):
        cfg = load_config(vault_root=tmp_vault)
        results = search("auth", cfg)
        for r in results:
            assert r.source_type in ("journal", "vault")
            assert isinstance(r.message, str)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/claw-librarian && python -m pytest tests/test_query.py::TestQueryEngine -v`
Expected: FAIL

- [ ] **Step 3: Implement query engine**

`claw_librarian/query/engine.py`:
```python
"""Query engine — search journal + vault, rank by freshness."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from claw_librarian.config import Config
from claw_librarian.journal.reader import read_entries, filter_entries
from claw_librarian.graph.wikilinks import find_all_vault_files


@dataclass
class SearchResult:
    """A single search result."""
    source_type: str  # "journal" or "vault"
    message: str
    timestamp: str
    agent: str | None = None
    project: str | None = None
    file_path: str | None = None
    line_num: int | None = None
    entry_id: str | None = None
    refs: list[str] | None = None
    link_density: int = 0


def search(
    query: str,
    config: Config,
    *,
    project: str | None = None,
    agent: str | None = None,
    since: str | None = None,
    depth: int | None = None,
) -> list[SearchResult]:
    """Search journal and vault Markdown files.

    Returns results sorted by freshness (newest first).
    """
    results: list[SearchResult] = []
    pattern = re.compile(re.escape(query), re.IGNORECASE) if query else None

    # Phase 1a: Search journal
    entries = filter_entries(
        read_entries(config.journal_path),
        project=project,
        agent=agent,
        since=since,
    )
    for entry in entries:
        if pattern is None or pattern.search(entry.message) or any(
            pattern.search(t) for t in entry.tags
        ):
            results.append(SearchResult(
                source_type="journal",
                message=entry.message,
                timestamp=entry.timestamp,
                agent=entry.agent,
                project=entry.project,
                entry_id=entry.id,
                refs=entry.refs,
            ))

    # Phase 1b: Search vault Markdown files
    if query:  # Only grep vault if there's a search term
        vault_files = find_all_vault_files(config.vault_root)
        for f in vault_files:
            try:
                text = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for line_num, line in enumerate(text.split("\n"), 1):
                if pattern.search(line):
                    rel_path = str(f.relative_to(config.vault_root))
                    results.append(SearchResult(
                        source_type="vault",
                        message=line.strip(),
                        timestamp="",  # vault files don't have per-line timestamps
                        file_path=rel_path,
                        line_num=line_num,
                    ))
                    break  # One hit per file

    # Sort: journal hits by freshness, vault hits after
    journal_hits = sorted(
        [r for r in results if r.source_type == "journal"],
        key=lambda r: r.timestamp,
        reverse=True,
    )
    vault_hits = [r for r in results if r.source_type == "vault"]

    return journal_hits + vault_hits
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claw-librarian && python -m pytest tests/test_query.py::TestQueryEngine -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add claw_librarian/query/engine.py tests/test_query.py
git commit -m "feat: query engine with journal + vault search and freshness ranking"
```

---

### Task 15: Graph expander (1-hop)

**Files:**
- Create: `claw_librarian/query/expander.py`
- Test: `tests/test_query.py` (append to)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_query.py`:
```python
from claw_librarian.query.expander import expand_results
from claw_librarian.query.engine import SearchResult


class TestExpander:
    def test_expand_with_refs(self, vault_with_files):
        cfg = load_config(vault_root=vault_with_files)
        (vault_with_files / "journal.jsonl").touch()
        results = [
            SearchResult(
                source_type="journal",
                message="Found auth bug",
                timestamp="2026-03-15T14:00:00Z",
                refs=["projects/test-project/api-spec"],
            )
        ]
        expanded = expand_results(results, cfg, depth=1)
        related = [r for r in expanded if r.source_type == "related"]
        assert len(related) >= 1
        assert any("api-spec" in (r.file_path or "") for r in related)

    def test_expand_with_backlinks(self, vault_with_files):
        cfg = load_config(vault_root=vault_with_files)
        (vault_with_files / "journal.jsonl").touch()
        results = [
            SearchResult(
                source_type="vault",
                message="API Spec content",
                timestamp="",
                file_path="projects/test-project/api-spec.md",
            )
        ]
        expanded = expand_results(results, cfg, depth=1)
        related = [r for r in expanded if r.source_type == "related"]
        # tests.md links to api-spec, so it should appear
        assert any("tests" in (r.file_path or "") for r in related)

    def test_expand_depth_zero(self, vault_with_files):
        cfg = load_config(vault_root=vault_with_files)
        (vault_with_files / "journal.jsonl").touch()
        results = [
            SearchResult(
                source_type="journal",
                message="Test",
                timestamp="2026-03-15T14:00:00Z",
                refs=["projects/test-project/api-spec"],
            )
        ]
        expanded = expand_results(results, cfg, depth=0)
        related = [r for r in expanded if r.source_type == "related"]
        assert related == []

    def test_expand_deduplicates(self, vault_with_files):
        cfg = load_config(vault_root=vault_with_files)
        (vault_with_files / "journal.jsonl").touch()
        results = [
            SearchResult(
                source_type="journal", message="A",
                timestamp="2026-03-15T14:00:00Z",
                refs=["projects/test-project/api-spec"],
            ),
            SearchResult(
                source_type="journal", message="B",
                timestamp="2026-03-15T13:00:00Z",
                refs=["projects/test-project/api-spec"],
            ),
        ]
        expanded = expand_results(results, cfg, depth=1)
        related = [r for r in expanded if r.source_type == "related"]
        api_spec_hits = [r for r in related if "api-spec" in (r.file_path or "")]
        assert len(api_spec_hits) <= 1  # deduplicated
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/claw-librarian && python -m pytest tests/test_query.py::TestExpander -v`
Expected: FAIL

- [ ] **Step 3: Implement expander**

`claw_librarian/query/expander.py`:
```python
"""Graph expander — follow wikilinks 1 hop from search results."""

from __future__ import annotations

from pathlib import Path

from claw_librarian.config import Config
from claw_librarian.graph.wikilinks import (
    resolve_ref,
    find_all_vault_files,
    extract_wikilinks,
)
from claw_librarian.graph.backlinks import incoming_links
from claw_librarian.graph.frontmatter import parse_file
from .engine import SearchResult


def expand_results(
    results: list[SearchResult],
    config: Config,
    depth: int = 1,
) -> list[SearchResult]:
    """Expand search results with related nodes via wikilink graph.

    Returns original results + related nodes (deduplicated).
    """
    if depth == 0:
        return results

    vault_files = find_all_vault_files(config.vault_root)
    seen_paths: set[str] = set()
    related: list[SearchResult] = []

    # Collect existing result paths to avoid duplicating
    for r in results:
        if r.file_path:
            seen_paths.add(r.file_path)

    def _add_related(path: Path, link_density: int) -> None:
        rel = str(path.relative_to(config.vault_root))
        if rel in seen_paths:
            return
        seen_paths.add(rel)
        meta, _ = parse_file(path)
        title = meta.get("title", path.stem) if meta else path.stem
        updated = meta.get("updated", "") if meta else ""
        note_type = meta.get("type", "") if meta else ""
        related.append(SearchResult(
            source_type="related",
            message=f"[[{rel.removesuffix('.md')}]] — {title}",
            timestamp=str(updated),
            file_path=rel,
            link_density=link_density,
        ))

    for result in results:
        # Expand forward refs from journal entries
        if result.refs:
            for ref in result.refs:
                resolved = resolve_ref(ref, config.vault_root, vault_files)
                if resolved and resolved.exists():
                    _add_related(resolved, link_density=1)

        # Expand from vault file hits — follow outgoing links
        if result.file_path:
            full_path = config.vault_root / result.file_path
            if full_path.exists():
                try:
                    text = full_path.read_text(encoding="utf-8")
                    links = extract_wikilinks(text)
                    for link in links:
                        resolved = resolve_ref(link, config.vault_root, vault_files)
                        if resolved and resolved.exists():
                            _add_related(resolved, link_density=1)
                except (OSError, UnicodeDecodeError):
                    pass

                # Expand backlinks — files that link TO this hit
                sources = incoming_links(full_path, config.vault_root, vault_files)
                for source in sources:
                    _add_related(source, link_density=1)

    # Sort related by link_density (descending)
    related.sort(key=lambda r: r.link_density, reverse=True)

    return results + related
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claw-librarian && python -m pytest tests/test_query.py::TestExpander -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add claw_librarian/query/expander.py tests/test_query.py
git commit -m "feat: graph expander with forward ref + backlink 1-hop expansion"
```

---

## Chunk 6: CLI + OpenClaw Adapter

### Task 16: CLI entry point

**Files:**
- Create: `claw_librarian/cli/main.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_cli.py`:
```python
"""CLI integration tests."""

import json
import subprocess
import sys
from pathlib import Path


def run_claw(args: list[str], vault: Path, stdin_data: str | None = None) -> subprocess.CompletedProcess:
    """Run the claw CLI pointing at a test vault."""
    env_args = ["--vault", str(vault)]
    cmd = [sys.executable, "-m", "claw_librarian.cli.main"] + args + env_args
    return subprocess.run(
        cmd, capture_output=True, text=True,
        input=stdin_data, timeout=10,
    )


class TestCLICollect:
    def test_collect_basic(self, tmp_vault):
        result = run_claw(
            ["collect", "--agent", "test", "Hello world"],
            tmp_vault,
        )
        assert result.returncode == 0
        assert len(result.stdout.strip()) == 26  # ULID
        journal = tmp_vault / "journal.jsonl"
        assert journal.exists()
        entry = json.loads(journal.read_text().strip())
        assert entry["message"] == "Hello world"

    def test_collect_with_options(self, tmp_vault):
        result = run_claw(
            ["collect", "--agent", "cipher", "--project", "test",
             "--type", "milestone", "--tag", "auth",
             "--ref", "projects/test/spec", "Did the thing"],
            tmp_vault,
        )
        assert result.returncode == 0

    def test_collect_stdin(self, tmp_vault):
        result = run_claw(
            ["collect", "--agent", "atlas", "--stdin"],
            tmp_vault,
            stdin_data="Piped message",
        )
        assert result.returncode == 0
        entry = json.loads((tmp_vault / "journal.jsonl").read_text().strip())
        assert entry["message"] == "Piped message"

    def test_collect_stdin_and_positional_errors(self, tmp_vault):
        result = run_claw(
            ["collect", "--agent", "test", "--stdin", "Conflict"],
            tmp_vault,
            stdin_data="Also piped",
        )
        assert result.returncode == 1


class TestCLIIndex:
    def test_index_creates_map(self, tmp_vault):
        # First collect something
        run_claw(["collect", "--agent", "a", "Test msg"], tmp_vault)
        result = run_claw(["index"], tmp_vault)
        assert result.returncode == 0
        assert (tmp_vault / "MAP.md").exists()

    def test_index_full_rebuild(self, tmp_vault):
        run_claw(["collect", "--agent", "a", "Msg"], tmp_vault)
        result = run_claw(["index", "--full"], tmp_vault)
        assert result.returncode == 0


class TestCLIQuery:
    def test_query_basic(self, tmp_vault):
        run_claw(["collect", "--agent", "a", "Auth bug found"], tmp_vault)
        result = run_claw(["query", "auth"], tmp_vault)
        assert result.returncode == 0
        assert "auth" in result.stdout.lower() or "Auth" in result.stdout

    def test_query_json_format(self, tmp_vault):
        run_claw(["collect", "--agent", "a", "Auth bug"], tmp_vault)
        result = run_claw(["query", "auth", "--format", "json"], tmp_vault)
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert isinstance(parsed, list)

    def test_query_no_results(self, tmp_vault):
        (tmp_vault / "journal.jsonl").touch()
        result = run_claw(["query", "xyznonexistent"], tmp_vault)
        assert result.returncode == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/claw-librarian && python -m pytest tests/test_cli.py -v`
Expected: FAIL

- [ ] **Step 3: Implement CLI**

`claw_librarian/cli/main.py`:
```python
"""CLI entry point: claw collect|index|query."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from claw_librarian.config import load_config
from claw_librarian.journal.writer import collect
from claw_librarian.index.indexer import run_index
from claw_librarian.query.engine import search
from claw_librarian.query.expander import expand_results


def cmd_collect(args: argparse.Namespace) -> int:
    """Handle 'claw collect' command."""
    config = load_config(vault_root=args.vault)

    # Handle stdin vs positional message
    if args.stdin and args.message:
        print("error: cannot use --stdin with a positional message", file=sys.stderr)
        return 1
    if args.stdin:
        if sys.stdin.isatty():
            print("error: --stdin requires piped input", file=sys.stderr)
            return 1
        message = sys.stdin.read().strip()
    elif args.message:
        message = " ".join(args.message)
    else:
        print("error: message required (positional or --stdin)", file=sys.stderr)
        return 1

    if not message:
        print("error: message cannot be empty", file=sys.stderr)
        return 1

    agent = args.agent or config.default_agent
    if not agent:
        print("error: --agent required (or set default_agent in config)", file=sys.stderr)
        return 1

    entry_id = collect(
        journal_path=config.journal_path,
        agent=agent,
        message=message,
        project=args.project,
        entry_type=args.type,
        refs=args.ref or [],
        tags=args.tag or [],
    )
    print(entry_id)
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    """Handle 'claw index' command."""
    config = load_config(vault_root=args.vault)
    run_index(config, full=args.full)
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    """Handle 'claw query' command."""
    config = load_config(vault_root=args.vault)
    depth = args.depth if args.depth is not None else config.default_depth
    fmt = args.format or config.default_format

    results = search(
        args.query,
        config,
        project=args.project,
        agent=args.agent,
        since=args.since,
    )
    results = expand_results(results, config, depth=depth)

    if fmt == "json":
        output = []
        for r in results:
            output.append({
                "source_type": r.source_type,
                "message": r.message,
                "timestamp": r.timestamp,
                "agent": r.agent,
                "project": r.project,
                "file_path": r.file_path,
                "line_num": r.line_num,
                "entry_id": r.entry_id,
                "link_density": r.link_density,
            })
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        # Brief format
        direct = [r for r in results if r.source_type in ("journal", "vault")]
        related = [r for r in results if r.source_type == "related"]

        if not direct and not related:
            print("No results found.")
            return 0

        if direct:
            print(f"--- Direct Hits ({len(direct)}) ---")
            for r in direct:
                if r.source_type == "journal":
                    print(f"[{r.timestamp[:16]}] {r.agent}/{r.project or 'cross'} ({r.entry_id})")
                    print(f"  {r.message}")
                    if r.refs:
                        print(f"  refs: {', '.join(r.refs)}")
                else:
                    print(f"{r.file_path}:{r.line_num}")
                    print(f"  {r.message}")
                print()

        if related:
            print(f"--- Related Nodes ({len(related)}) ---")
            for r in related:
                print(f"  {r.message}")
            print()

    return 0


def main(argv: list[str] | None = None) -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="claw",
        description="File-native memory coordination for multi-agent teams",
    )
    parser.add_argument("--vault", type=Path, help="Vault root directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # collect
    p_collect = subparsers.add_parser("collect", help="Record a journal entry")
    p_collect.add_argument("message", nargs="*", help="Entry message")
    p_collect.add_argument("--agent", help="Agent name")
    p_collect.add_argument("--project", help="Project name")
    p_collect.add_argument("--type", default="note", choices=[
        "milestone", "discovery", "decision", "handoff", "error", "note",
    ])
    p_collect.add_argument("--ref", action="append", help="Related vault ref")
    p_collect.add_argument("--tag", action="append", help="Tag")
    p_collect.add_argument("--stdin", action="store_true", help="Read message from stdin")

    # index
    p_index = subparsers.add_parser("index", help="Build materialized views")
    p_index.add_argument("--full", action="store_true", help="Full rebuild")

    # query
    p_query = subparsers.add_parser("query", help="Search journal and vault")
    p_query.add_argument("query", help="Search query")
    p_query.add_argument("--project", help="Filter by project")
    p_query.add_argument("--agent", help="Filter by agent")
    p_query.add_argument("--since", help="Filter by date (YYYY-MM-DD)")
    p_query.add_argument("--depth", type=int, help="Graph expansion depth")
    p_query.add_argument("--format", choices=["brief", "json"], help="Output format")

    args = parser.parse_args(argv)

    handlers = {
        "collect": cmd_collect,
        "index": cmd_index,
        "query": cmd_query,
    }
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claw-librarian && python -m pytest tests/test_cli.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add claw_librarian/cli/main.py tests/test_cli.py
git commit -m "feat: CLI with collect, index, query subcommands"
```

---

### Task 17: OpenClaw adapter

**Files:**
- Create: `claw_librarian/adapters/openclaw/adapter.py`
- Create: `claw_librarian/adapters/openclaw/defaults.toml`
- Test: `tests/test_adapter.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_adapter.py`:
```python
"""Tests for OpenClaw adapter."""

from pathlib import Path

from claw_librarian.adapters.openclaw.adapter import (
    OpenClawAdapter,
    bridge_inbox_file,
    discover_agents,
)
from claw_librarian.config import load_config


class TestOpenClawAdapter:
    def test_adapter_creates_config(self, tmp_vault):
        adapter = OpenClawAdapter(vault_root=tmp_vault)
        cfg = adapter.config
        assert cfg.vault_root == tmp_vault

    def test_discover_agents(self, vault_with_files):
        agents = discover_agents(vault_with_files)
        assert "cipher" in agents

    def test_bridge_inbox_creates_journal_entry(self, tmp_vault):
        inbox = tmp_vault / "_inbox"
        inbox.mkdir()
        inbox_file = inbox / "test-entry.md"
        inbox_file.write_text(
            "---\nfrom: cipher\ndate: 2026-03-15\nproject: test-project\naction: update\n---\n\n"
            "Finished the auth module.\n"
        )
        cfg = load_config(vault_root=tmp_vault)
        entry_id = bridge_inbox_file(inbox_file, cfg)
        assert entry_id is not None
        assert len(entry_id) == 26
        # Journal should have entry
        assert cfg.journal_path.exists()
        # Inbox file should be stamped
        content = inbox_file.read_text()
        assert "journal_id" in content

    def test_bridge_skips_already_stamped(self, tmp_vault):
        inbox = tmp_vault / "_inbox"
        inbox.mkdir()
        inbox_file = inbox / "stamped.md"
        inbox_file.write_text(
            "---\nfrom: cipher\ndate: 2026-03-15\nproject: test\naction: update\n"
            "journal_id: 01EXISTING\n---\n\nContent.\n"
        )
        cfg = load_config(vault_root=tmp_vault)
        entry_id = bridge_inbox_file(inbox_file, cfg)
        assert entry_id is None  # Skipped

    def test_bridge_bad_frontmatter(self, tmp_vault):
        inbox = tmp_vault / "_inbox"
        inbox.mkdir()
        inbox_file = inbox / "bad.md"
        inbox_file.write_text("No frontmatter here.\n")
        cfg = load_config(vault_root=tmp_vault)
        entry_id = bridge_inbox_file(inbox_file, cfg)
        assert entry_id is None
```

- [ ] **Step 2: Run to verify failure**

Run: `cd ~/claw-librarian && python -m pytest tests/test_adapter.py -v`
Expected: FAIL

- [ ] **Step 3: Implement adapter**

`claw_librarian/adapters/openclaw/defaults.toml`:
```toml
[vault]
journal = "journal.jsonl"

[inbox]
enabled = true
dir = "_inbox"
processed_dir = "_inbox/_processed"
review_dir = "_inbox/_review"

[agents]
discovery = "team/*.md"
```

`claw_librarian/adapters/openclaw/adapter.py`:
```python
"""OpenClaw adapter — inbox bridge, agent identity, config preset."""

from __future__ import annotations

from pathlib import Path

from claw_librarian.config import Config, load_config
from claw_librarian.graph.frontmatter import parse_file, parse, serialize
from claw_librarian.journal.writer import collect


# Map inbox 'action' to journal event types
ACTION_TO_TYPE = {
    "update": "milestone",
    "create": "milestone",
    "log": "note",
}


class OpenClawAdapter:
    """Adapter for the OpenClaw/SystemVault ecosystem."""

    def __init__(self, vault_root: Path) -> None:
        self.vault_root = vault_root
        self.config = load_config(vault_root=vault_root)

    def bridge_inbox(self) -> list[str]:
        """Process all pending inbox files. Returns list of journal entry IDs."""
        inbox_dir = self.vault_root / "_inbox"
        if not inbox_dir.exists():
            return []
        entry_ids = []
        for f in sorted(inbox_dir.glob("*.md")):
            entry_id = bridge_inbox_file(f, self.config)
            if entry_id:
                entry_ids.append(entry_id)
        return entry_ids


def bridge_inbox_file(inbox_file: Path, config: Config) -> str | None:
    """Bridge a single inbox .md file into the journal.

    Returns the journal entry ID, or None if skipped.
    """
    meta, body = parse_file(inbox_file)
    if meta is None:
        return None

    # Skip already-stamped files
    if "journal_id" in meta:
        return None

    # Extract fields
    agent = meta.get("from", "unknown")
    project = meta.get("project")
    action = meta.get("action", "note")
    entry_type = ACTION_TO_TYPE.get(action, "note")
    message = body.strip()
    if not message:
        message = f"[{action}] from {agent}"

    entry_id = collect(
        journal_path=config.journal_path,
        agent=agent,
        message=message,
        project=project,
        entry_type=entry_type,
    )

    # Stamp the inbox file with journal_id
    meta["journal_id"] = entry_id
    stamped = serialize(meta, body)
    inbox_file.write_text(stamped, encoding="utf-8")

    return entry_id


def discover_agents(vault_root: Path) -> list[str]:
    """Discover agent names from team/*.md files."""
    team_dir = vault_root / "team"
    if not team_dir.exists():
        return []
    return [f.stem for f in team_dir.glob("*.md")]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claw-librarian && python -m pytest tests/test_adapter.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add claw_librarian/adapters/openclaw/ tests/test_adapter.py
git commit -m "feat: OpenClaw adapter with inbox bridge and agent discovery"
```

---

## Chunk 7: Integration Test + README + Security Review

### Task 18: Integration test (full round-trip)

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
"""Full round-trip integration test: collect → index → query."""

import json
import subprocess
import sys
from pathlib import Path


def run_claw(args, vault, stdin_data=None):
    cmd = [sys.executable, "-m", "claw_librarian.cli.main"] + args + ["--vault", str(vault)]
    return subprocess.run(cmd, capture_output=True, text=True, input=stdin_data, timeout=10)


class TestIntegration:
    def test_full_round_trip(self, tmp_vault):
        """collect → index → query — the core value proposition."""
        # Agent 1 collects work
        r = run_claw([
            "collect", "--agent", "cipher", "--project", "demo",
            "--type", "milestone", "Completed auth test suite"
        ], tmp_vault)
        assert r.returncode == 0
        id1 = r.stdout.strip()

        # Agent 2 collects work
        r = run_claw([
            "collect", "--agent", "atlas", "--project", "demo",
            "--type", "handoff", "Passing API work to cipher"
        ], tmp_vault)
        assert r.returncode == 0

        # Run indexer
        r = run_claw(["index"], tmp_vault)
        assert r.returncode == 0

        # Verify MAP.md
        map_path = tmp_vault / "MAP.md"
        assert map_path.exists()
        map_content = map_path.read_text()
        assert "demo" in map_content
        assert "cipher" in map_content
        assert "atlas" in map_content

        # Verify context.md
        ctx = tmp_vault / "projects" / "demo" / "context.md"
        assert ctx.exists()
        ctx_content = ctx.read_text()
        assert "Completed auth test suite" in ctx_content
        assert "Passing API work to cipher" in ctx_content

        # Query
        r = run_claw(["query", "auth", "--format", "json"], tmp_vault)
        assert r.returncode == 0
        results = json.loads(r.stdout)
        assert len(results) >= 1
        assert any("auth" in r["message"].lower() for r in results)

    def test_incremental_index(self, tmp_vault):
        """Index picks up only new entries on second run."""
        run_claw(["collect", "--agent", "a", "First"], tmp_vault)
        run_claw(["index"], tmp_vault)

        state_path = tmp_vault / ".claw-librarian-state.json"
        state1 = json.loads(state_path.read_text())

        run_claw(["collect", "--agent", "b", "Second"], tmp_vault)
        run_claw(["index"], tmp_vault)

        state2 = json.loads(state_path.read_text())
        assert state2["last_indexed_id"] != state1["last_indexed_id"]
```

- [ ] **Step 2: Run integration tests**

Run: `cd ~/claw-librarian && python -m pytest tests/test_integration.py -v`
Expected: 2 passed

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: full round-trip integration test (collect → index → query)"
```

---

### Task 19: README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write README**

Update `~/claw-librarian/README.md` with:
- Project description and tagline
- Installation (`pip install -e .`)
- Quick start (collect → index → query examples)
- Architecture overview (the data flow diagram from the spec)
- Configuration section
- Contributing section
- License (MIT)

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with quickstart, architecture, and configuration"
```

---

### Task 20: Run full test suite

- [ ] **Step 1: Run all tests**

Run: `cd ~/claw-librarian && python -m pytest tests/ -v --tb=short`
Expected: All tests pass

- [ ] **Step 2: Fix any failures**

If any tests fail, fix them before proceeding.

---

### Task 21: Security review

- [ ] **Step 1: Run security review using code-reviewer agent**

Focus areas:
- **Path traversal:** Ensure `resolve_ref()` and any user-provided paths can't escape the vault root (e.g., `../../etc/passwd`)
- **Command injection:** The CLI uses argparse (safe), but verify no user input reaches shell execution
- **File locking:** Verify the fcntl locking prevents corruption under concurrent access
- **JSONL injection:** Ensure `to_json_line()` properly escapes all content (no newline injection)
- **Denial of service:** Verify large inputs don't cause unbounded memory usage (streaming reader)
- **Frontmatter parsing:** Verify no code execution through YAML parsing (we use regex, not PyYAML `load()`)

- [ ] **Step 2: Fix any security issues found**

- [ ] **Step 3: Commit fixes**

```bash
git commit -m "security: address findings from security review"
```

---

### Task 22: Create GitHub repo and PR

- [ ] **Step 1: Create GitHub repository**

```bash
cd ~/claw-librarian
gh repo create claw-librarian --public --description "File-native memory coordination for multi-agent teams" --source .
```

- [ ] **Step 2: Push all commits**

```bash
git push -u origin master
```

- [ ] **Step 3: Verify on GitHub**

Confirm repo is visible, README renders, all code is present.
