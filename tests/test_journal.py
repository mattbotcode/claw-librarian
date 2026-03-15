"""Tests for journal module: ULID, schema, writer, reader."""

import time

from claw_librarian.journal._ulid import generate_ulid


class TestULID:
    def test_ulid_is_26_chars(self):
        uid = generate_ulid()
        assert len(uid) == 26

    def test_ulid_uses_crockford_base32(self):
        uid = generate_ulid()
        valid_chars = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
        assert all(c in valid_chars for c in uid)

    def test_ulid_is_sortable_by_time(self):
        uid1 = generate_ulid()
        time.sleep(0.002)  # 2ms gap
        uid2 = generate_ulid()
        assert uid2 > uid1

    def test_ulid_uniqueness(self):
        ids = {generate_ulid() for _ in range(1000)}
        assert len(ids) == 1000
