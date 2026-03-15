"""Graph expander — follow wikilinks 1 hop from search results."""

from __future__ import annotations

from pathlib import Path

from claw_librarian.config import Config
from claw_librarian.graph.wikilinks import (
    resolve_ref,
    find_all_vault_files,
    extract_wikilinks,
)
from claw_librarian.graph.backlinks import incoming_links
from claw_librarian.graph.frontmatter import parse_file
from .engine import SearchResult


def expand_results(
    results: list[SearchResult],
    config: Config,
    depth: int = 1,
) -> list[SearchResult]:
    """Expand search results with related nodes via wikilink graph.

    Returns original results + related nodes (deduplicated).
    """
    if depth == 0:
        return results

    vault_files = find_all_vault_files(config.vault_root)
    seen_paths: set[str] = set()
    related: list[SearchResult] = []

    # Collect existing result paths to avoid duplicating
    for r in results:
        if r.file_path:
            seen_paths.add(r.file_path)

    def _add_related(path: Path, link_density: int) -> None:
        rel = str(path.relative_to(config.vault_root))
        if rel in seen_paths:
            return
        seen_paths.add(rel)
        meta, _ = parse_file(path)
        title = meta.get("title", path.stem) if meta else path.stem
        updated = meta.get("updated", "") if meta else ""
        note_type = meta.get("type", "") if meta else ""
        related.append(SearchResult(
            source_type="related",
            message=f"[[{rel.removesuffix('.md')}]] — {title}",
            timestamp=str(updated),
            file_path=rel,
            link_density=link_density,
        ))

    for result in results:
        # Expand forward refs from journal entries
        if result.refs:
            for ref in result.refs:
                resolved = resolve_ref(ref, config.vault_root, vault_files)
                if resolved and resolved.exists():
                    _add_related(resolved, link_density=1)

        # Expand from vault file hits — follow outgoing links
        if result.file_path:
            full_path = config.vault_root / result.file_path
            if full_path.exists():
                try:
                    text = full_path.read_text(encoding="utf-8")
                    links = extract_wikilinks(text)
                    for link in links:
                        resolved = resolve_ref(link, config.vault_root, vault_files)
                        if resolved and resolved.exists():
                            _add_related(resolved, link_density=1)
                except (OSError, UnicodeDecodeError):
                    pass

                # Expand backlinks — files that link TO this hit
                sources = incoming_links(full_path, config.vault_root, vault_files)
                for source in sources:
                    _add_related(source, link_density=1)

    # Sort related by link_density (descending)
    related.sort(key=lambda r: r.link_density, reverse=True)

    return results + related
