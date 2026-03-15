"""Journal entry schema — dataclass, validation, serialization."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict

VALID_TYPES = frozenset({
    "milestone", "discovery", "decision", "handoff", "error", "note",
})

REQUIRED_FIELDS = {"schema_version", "id", "timestamp", "agent", "type", "message"}


@dataclass
class JournalEntry:
    """A single journal event."""

    schema_version: int
    id: str
    timestamp: str
    agent: str
    type: str
    message: str
    project: str | None = None
    refs: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_json_line(self) -> str:
        """Serialize to a single JSON line (no trailing newline)."""
        d = asdict(self)
        # Omit None project for cleaner output
        if d["project"] is None:
            d["project"] = None
        return json.dumps(d, ensure_ascii=False)

    @classmethod
    def from_json_line(cls, line: str) -> JournalEntry:
        """Deserialize from a JSON line."""
        d = json.loads(line)
        return cls(
            schema_version=d["schema_version"],
            id=d["id"],
            timestamp=d["timestamp"],
            agent=d["agent"],
            type=d["type"],
            message=d["message"],
            project=d.get("project"),
            refs=d.get("refs", []),
            tags=d.get("tags", []),
            metadata=d.get("metadata", {}),
        )


def validate_entry(data: dict) -> list[str]:
    """Validate a raw dict against the journal schema. Returns list of error strings."""
    errors = []
    for f in REQUIRED_FIELDS:
        if f not in data:
            errors.append(f"missing required field: {f}")
    if "type" in data and data["type"] not in VALID_TYPES:
        errors.append(f"invalid type: {data['type']} (valid: {', '.join(sorted(VALID_TYPES))})")
    if "schema_version" in data and data["schema_version"] != 1:
        errors.append(f"unsupported schema_version: {data['schema_version']}")
    return errors
