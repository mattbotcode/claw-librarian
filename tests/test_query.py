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
