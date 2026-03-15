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

    def test_bridge_inbox_scans_processed_dir(self, tmp_vault):
        """Adapter should also bridge files in _inbox/_processed/."""
        inbox = tmp_vault / "_inbox"
        processed = inbox / "_processed"
        processed.mkdir(parents=True)
        # File in _processed (moved there by process_inbox.py)
        processed_file = processed / "routed-entry.md"
        processed_file.write_text(
            "---\nfrom: optic\ndate: 2026-03-15\nproject: macro-model\naction: log\n---\n\n"
            "Retrained ridge model.\n"
        )
        adapter = OpenClawAdapter(vault_root=tmp_vault)
        ids = adapter.bridge_inbox()
        assert len(ids) == 1
        # File should now be stamped
        content = processed_file.read_text()
        assert "journal_id" in content
