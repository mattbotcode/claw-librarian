#!/usr/bin/env python3
"""Validate Obsidian canvas files — check that agent nodes resolve to vault .md files.

Parses JSON Canvas spec, extracts entity names from text nodes, and verifies
each maps to an existing note in the vault. Designed to run as part of the
librarian heartbeat or standalone.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.wikilinks import find_all_vault_files, resolve_wikilink

VAULT_ROOT = Path.home() / "SystemVault"
ARCHITECTURE_DIR = VAULT_ROOT / "architecture"


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def extract_entity_name(text: str) -> str | None:
    """Extract the primary name from a canvas node's markdown text.

    Looks for '# Name' or '## Name' headers, strips emoji.
    """
    # Only match h1/h2 headings — h3+ are decorative/structural nodes
    match = re.search(r"^#{1,2}\s+(.+)$", text, re.MULTILINE)
    if not match:
        return None
    name = match.group(1).strip()
    # Strip emoji and variation selectors (U+FE0E, U+FE0F)
    name = re.sub(r"[\U0001f300-\U0001f9ff\u2600-\u26ff\u2700-\u27bf\ufe0e\ufe0f]", "", name).strip()
    return name


def validate_canvas(canvas_path: Path, vault_files: list[Path] | None = None) -> dict:
    """Validate a single canvas file.

    Returns dict with:
        - resolved: list of (node_id, name, resolved_path)
        - broken: list of (node_id, name) where no .md found
        - skipped: list of (node_id, reason) for nodes without extractable names
    """
    if vault_files is None:
        vault_files = find_all_vault_files()

    with open(canvas_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    results = {"resolved": [], "broken": [], "skipped": []}

    for node in data.get("nodes", []):
        node_id = node.get("id", "unknown")
        node_type = node.get("type", "")

        # Only validate text nodes (file nodes have explicit paths)
        if node_type == "file":
            file_ref = node.get("file", "")
            target = VAULT_ROOT / file_ref
            if target.exists():
                results["resolved"].append((node_id, file_ref, str(target)))
            else:
                results["broken"].append((node_id, file_ref))
            continue

        if node_type != "text":
            results["skipped"].append((node_id, f"unsupported type: {node_type}"))
            continue

        text = node.get("text", "")
        name = extract_entity_name(text)
        if not name:
            results["skipped"].append((node_id, "no heading found"))
            continue

        # Try to resolve name to a vault file
        resolved = resolve_wikilink(name, vault_files)
        if resolved:
            results["resolved"].append((node_id, name, str(resolved)))
        else:
            # Try lowercase slug variant (e.g. "Atlas" -> "atlas")
            resolved = resolve_wikilink(name.lower(), vault_files)
            if resolved:
                results["resolved"].append((node_id, name, str(resolved)))
            else:
                results["broken"].append((node_id, name))

    return results


def validate_all_canvases(vault_files: list[Path] | None = None) -> dict[str, dict]:
    """Validate all .canvas files in the vault. Returns {path: results}."""
    if vault_files is None:
        vault_files = find_all_vault_files()

    all_results = {}
    for canvas in VAULT_ROOT.rglob("*.canvas"):
        # Skip .obsidian internal canvases
        if ".obsidian" in canvas.parts:
            continue
        try:
            results = validate_canvas(canvas, vault_files)
            all_results[str(canvas.relative_to(VAULT_ROOT))] = results
        except (json.JSONDecodeError, OSError) as e:
            log(f"  ERROR reading {canvas}: {e}")
            all_results[str(canvas.relative_to(VAULT_ROOT))] = {
                "resolved": [], "broken": [], "skipped": [],
                "error": str(e),
            }

    return all_results


def main() -> None:
    log("Validating canvas files")
    vault_files = find_all_vault_files()
    all_results = validate_all_canvases(vault_files)

    total_broken = 0
    for canvas_path, results in all_results.items():
        log(f"Canvas: {canvas_path}")
        if "error" in results:
            log(f"  ERROR: {results['error']}")
            continue

        for node_id, name, path in results["resolved"]:
            log(f"  OK: {name} -> {path}")
        for node_id, name in results["broken"]:
            log(f"  BROKEN: {name} (no matching .md)")
            total_broken += 1
        for node_id, reason in results["skipped"]:
            log(f"  SKIP: {node_id} ({reason})")

    if total_broken:
        log(f"Found {total_broken} broken canvas link(s)")
        sys.exit(1)
    else:
        log("All canvas links valid")


if __name__ == "__main__":
    main()
