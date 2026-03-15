"""CLI entry point: claw collect|index|query."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from claw_librarian.config import load_config
from claw_librarian.journal.writer import collect
from claw_librarian.index.indexer import run_index
from claw_librarian.query.engine import search
from claw_librarian.query.expander import expand_results


def cmd_collect(args: argparse.Namespace) -> int:
    """Handle 'claw collect' command."""
    config = load_config(vault_root=args.vault)

    # Handle stdin vs positional message
    if args.stdin and args.message:
        print("error: cannot use --stdin with a positional message", file=sys.stderr)
        return 1
    if args.stdin:
        if sys.stdin.isatty():
            print("error: --stdin requires piped input", file=sys.stderr)
            return 1
        MAX_MESSAGE_BYTES = 1_048_576  # 1 MB
        message = sys.stdin.read(MAX_MESSAGE_BYTES).strip()
    elif args.message:
        message = " ".join(args.message)
    else:
        print("error: message required (positional or --stdin)", file=sys.stderr)
        return 1

    if not message:
        print("error: message cannot be empty", file=sys.stderr)
        return 1

    agent = args.agent or config.default_agent
    if not agent:
        print("error: --agent required (or set default_agent in config)", file=sys.stderr)
        return 1

    entry_id = collect(
        journal_path=config.journal_path,
        agent=agent,
        message=message,
        project=args.project,
        entry_type=args.type,
        refs=args.ref or [],
        tags=args.tag or [],
    )
    print(entry_id)
    return 0


def cmd_index(args: argparse.Namespace) -> int:
    """Handle 'claw index' command."""
    config = load_config(vault_root=args.vault)
    run_index(config, full=args.full)
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    """Handle 'claw query' command."""
    config = load_config(vault_root=args.vault)
    depth = args.depth if args.depth is not None else config.default_depth
    fmt = args.format or config.default_format

    results = search(
        args.query,
        config,
        project=args.project,
        agent=args.agent,
        since=args.since,
    )
    results = expand_results(results, config, depth=depth)

    if fmt == "json":
        output = []
        for r in results:
            output.append({
                "source_type": r.source_type,
                "message": r.message,
                "timestamp": r.timestamp,
                "agent": r.agent,
                "project": r.project,
                "file_path": r.file_path,
                "line_num": r.line_num,
                "entry_id": r.entry_id,
                "link_density": r.link_density,
            })
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        # Brief format
        direct = [r for r in results if r.source_type in ("journal", "vault")]
        related = [r for r in results if r.source_type == "related"]

        if not direct and not related:
            print("No results found.")
            return 0

        if direct:
            print(f"--- Direct Hits ({len(direct)}) ---")
            for r in direct:
                if r.source_type == "journal":
                    print(f"[{r.timestamp[:16]}] {r.agent}/{r.project or 'cross'} ({r.entry_id})")
                    print(f"  {r.message}")
                    if r.refs:
                        print(f"  refs: {', '.join(r.refs)}")
                else:
                    print(f"{r.file_path}:{r.line_num}")
                    print(f"  {r.message}")
                print()

        if related:
            print(f"--- Related Nodes ({len(related)}) ---")
            for r in related:
                print(f"  {r.message}")
            print()

    return 0


def main(argv: list[str] | None = None) -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="claw",
        description="File-native memory coordination for multi-agent teams",
    )
    parser.add_argument("--vault", type=lambda p: Path(p).expanduser(), default=Path("~/SystemVault").expanduser(), help="Vault root directory")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # collect
    p_collect = subparsers.add_parser("collect", help="Record a journal entry")
    p_collect.add_argument("message", nargs="*", help="Entry message")
    p_collect.add_argument("--agent", help="Agent name")
    p_collect.add_argument("--project", help="Project name")
    p_collect.add_argument("--type", default="note", choices=[
        "milestone", "discovery", "decision", "handoff", "error", "note",
    ])
    p_collect.add_argument("--ref", action="append", help="Related vault ref")
    p_collect.add_argument("--tag", action="append", help="Tag")
    p_collect.add_argument("--stdin", action="store_true", help="Read message from stdin")

    # index
    p_index = subparsers.add_parser("index", help="Build materialized views")
    p_index.add_argument("--full", action="store_true", help="Full rebuild")

    # query
    p_query = subparsers.add_parser("query", help="Search journal and vault")
    p_query.add_argument("query", help="Search query")
    p_query.add_argument("--project", help="Filter by project")
    p_query.add_argument("--agent", help="Filter by agent")
    p_query.add_argument("--since", help="Filter by date (YYYY-MM-DD)")
    p_query.add_argument("--depth", type=int, help="Graph expansion depth")
    p_query.add_argument("--format", choices=["brief", "json"], help="Output format")

    args = parser.parse_args(argv)

    handlers = {
        "collect": cmd_collect,
        "index": cmd_index,
        "query": cmd_query,
    }
    sys.exit(handlers[args.command](args))


if __name__ == "__main__":
    main()
