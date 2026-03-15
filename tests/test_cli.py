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
