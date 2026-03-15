"""Minimal ULID generator — no external dependencies.

ULID = 48-bit ms timestamp (Crockford Base32) + 80-bit random.
Total: 26 characters, lexicographically sortable by time.
"""

import os
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_ulid() -> str:
    """Generate a new ULID string."""
    # Timestamp: milliseconds since Unix epoch, 10 chars
    ts_ms = int(time.time() * 1000)
    ts_chars = []
    for _ in range(10):
        ts_chars.append(_CROCKFORD[ts_ms & 0x1F])
        ts_ms >>= 5
    ts_part = "".join(reversed(ts_chars))

    # Randomness: 80 bits = 10 bytes, 16 chars
    rand_bytes = os.urandom(10)
    rand_val = int.from_bytes(rand_bytes, "big")
    rand_chars = []
    for _ in range(16):
        rand_chars.append(_CROCKFORD[rand_val & 0x1F])
        rand_val >>= 5
    rand_part = "".join(reversed(rand_chars))

    return ts_part + rand_part
