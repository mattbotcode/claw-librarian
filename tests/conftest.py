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
