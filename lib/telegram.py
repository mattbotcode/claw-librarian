"""Telegram notification helper — reuses existing bot token pattern."""

import json
import os
import urllib.request
import urllib.error
from pathlib import Path

ENV_FILE = Path.home() / ".openclaw" / ".env"
MATT_CHAT_ID = "7881574513"


def _load_env() -> dict[str, str]:
    """Load key=value pairs from ~/.openclaw/.env"""
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
    return env


def send_message(text: str, chat_id: str = MATT_CHAT_ID,
                 token_env: str = "KINGPIN_TELEGRAM_BOT_TOKEN") -> bool:
    """Send a Telegram message. Returns True on success."""
    env = _load_env()
    token = os.environ.get(token_env) or env.get(token_env)
    if not token:
        print(f"[telegram] Missing {token_env}")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode()

    req = urllib.request.Request(url, data=payload,
                                headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError) as e:
        print(f"[telegram] Send failed: {e}")
        return False
