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
