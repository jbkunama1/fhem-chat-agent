from __future__ import annotations

import pytest

from app.db import Database


def test_wrong_user_conversation_and_replay_and_nonce(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))
    cid = db.create_conversation("alice")
    pending = db.add_pending_action(cid, "alice", "fhem_set", {"a": 1}, "dest", "mcp", ttl_seconds=120)

    with pytest.raises(PermissionError):
        db.consume_pending(pending.id, "bob", cid, pending.nonce, "approved")

    with pytest.raises(PermissionError):
        db.consume_pending(pending.id, "alice", "other", pending.nonce, "approved")

    with pytest.raises(PermissionError):
        db.consume_pending(pending.id, "alice", cid, "wrong", "approved")

    consumed = db.consume_pending(pending.id, "alice", cid, pending.nonce, "approved")
    assert consumed.id == pending.id

    with pytest.raises(PermissionError):
        db.consume_pending(pending.id, "alice", cid, pending.nonce, "approved")


def test_expired_pending_action(tmp_path):
    db = Database(str(tmp_path / "db.sqlite"))
    cid = db.create_conversation("alice")
    pending = db.add_pending_action(cid, "alice", "fhem_set", {}, "dest", "mcp", ttl_seconds=-1)
    with pytest.raises(TimeoutError):
        db.consume_pending(pending.id, "alice", cid, pending.nonce, "approved")
