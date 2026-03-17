#!/usr/bin/env bash
# Librarian pipeline — runs inbox processing, adapter bridge, and ~/.local/bin/claw index.
set -euo pipefail

VAULT="$HOME/SystemVault"
SKILL_DIR="$HOME/.openclaw/workspace/skills/claw-librarian"
SKILL_SCRIPTS_DIR="$SKILL_DIR/scripts"

# Set PYTHONPATH to include the skill root so 'lib' is discoverable
export PYTHONPATH="$SKILL_DIR${PYTHONPATH:+:$PYTHONPATH}"

# Step 1: Process inbox (existing routing logic)
python3 "$SKILL_SCRIPTS_DIR/process_inbox.py"

# Step 2: Bridge any remaining inbox files into claw journal
# export PYTHONPATH=$PYTHONPATH:$HOME/.openclaw/workspace/skills/claw-librarian/
# python3 -c "
# from pathlib import Path
# from lib.claw_librarian.adapters.openclaw.adapter import OpenClawAdapter
# adapter = OpenClawAdapter(vault_root=Path('$VAULT').expanduser())
# ids = adapter.bridge_inbox()
# if ids:
#     print(f'[claw] Bridged {len(ids)} inbox entries to journal')
# "

# Step 3: Incremental index rebuild
~/.local/bin/claw index