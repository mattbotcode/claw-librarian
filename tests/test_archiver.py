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
