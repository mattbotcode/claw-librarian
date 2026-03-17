#!/usr/bin/env python3
"""
extract_claude_sessions.py — Extract Claude Code session summaries for a given date.

Reads ~/.claude/history.jsonl and outputs markdown grouped by session.
Used by the daily activity log cron to include Claude Code activity.

Usage:
  python3 extract_claude_sessions.py              # today
  python3 extract_claude_sessions.py 2026-03-03   # specific date
"""

import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HISTORY_FILE = Path.home() / '.claude' / 'history.jsonl'


def extract(target_date: str) -> str:
    """Extract Claude Code sessions for a date, return markdown."""
    if not HISTORY_FILE.is_file():
        return ''

    # Group prompts by sessionId for the target date
    sessions = defaultdict(list)
    with open(HISTORY_FILE, encoding='utf-8') as f:
        for line in f:
            entry = json.loads(line)
            ts = entry.get('timestamp', 0)
            d = datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d')
            if d != target_date:
                continue
            display = entry.get('display', '').strip()
            sid = entry.get('sessionId', '')
            if not display or not sid:
                continue
            if display.startswith('/') and len(display) < 20:
                continue
            sessions[sid].append({
                'text': display[:120],
                'time': datetime.fromtimestamp(ts / 1000).strftime('%I:%M %p'),
            })

    if not sessions:
        return ''

    total = sum(len(v) for v in sessions.values())
    lines = [
        f'## Claude Code Sessions',
        f'',
        f'*{len(sessions)} session(s), {total} prompt(s)*',
        '',
    ]

    for i, (sid, prompts) in enumerate(sessions.items(), 1):
        first_time = prompts[0]['time'] if prompts else ''
        lines.append(f'### Session {i} (started {first_time})')
        for p in prompts[:10]:
            lines.append(f'- `{p["time"]}` {p["text"]}')
        if len(prompts) > 10:
            lines.append(f'- *... +{len(prompts) - 10} more*')
        lines.append('')

    return '\n'.join(lines)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        date = sys.argv[1]
    else:
        date = datetime.now().strftime('%Y-%m-%d')
    result = extract(date)
    if result:
        print(result)
    else:
        print(f'No Claude Code sessions found for {date}')
