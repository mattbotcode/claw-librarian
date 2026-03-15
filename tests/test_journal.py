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


from claw_librarian.journal.writer import collect


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
