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
