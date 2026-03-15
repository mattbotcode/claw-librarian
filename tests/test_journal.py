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
