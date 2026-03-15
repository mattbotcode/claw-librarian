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
