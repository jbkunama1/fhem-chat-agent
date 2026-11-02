from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class PendingAction:
    id: str
    conversation_id: str
    owner: str
    tool_name: str
    tool_args_json: str
    destination: str
    transport: str
    expires_at: int
    nonce: str


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    @contextmanager
    def tx(self):
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def _init_schema(self) -> None:
        with self.tx() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audits (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS pending_actions (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    owner TEXT NOT NULL,
                    tool_name TEXT NOT NULL,
                    tool_args_json TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    transport TEXT NOT NULL,
                    nonce TEXT NOT NULL,
                    status TEXT NOT NULL,
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    consumed_at INTEGER
                );
                """
            )

    def cancel_pending_on_startup(self) -> None:
        now = int(time.time())
        with self.tx() as con:
            con.execute(
                "UPDATE pending_actions SET status='cancelled', consumed_at=? WHERE status='pending'",
                (now,),
            )

    def create_conversation(self, owner: str) -> str:
        conv_id = str(uuid.uuid4())
        now = int(time.time())
        with self.tx() as con:
            con.execute(
                "INSERT INTO conversations (id, owner, created_at) VALUES (?, ?, ?)",
                (conv_id, owner, now),
            )
        return conv_id

    def ensure_conversation(self, conversation_id: str, owner: str) -> None:
        row = self._conn.execute(
            "SELECT id FROM conversations WHERE id=? AND owner=?",
            (conversation_id, owner),
        ).fetchone()
        if not row:
            raise PermissionError("Konversation nicht gefunden oder nicht erlaubt")

    def add_message(self, conversation_id: str, role: str, content: str) -> str:
        mid = str(uuid.uuid4())
        now = int(time.time())
        with self.tx() as con:
            con.execute(
                "INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (mid, conversation_id, role, content, now),
            )
        return mid

    def get_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT role, content FROM messages WHERE conversation_id=? ORDER BY created_at, id",
            (conversation_id,),
        ).fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    def list_conversations(self, owner: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, created_at FROM conversations WHERE owner=? ORDER BY created_at DESC",
            (owner,),
        ).fetchall()
        return [{"id": r["id"], "created_at": r["created_at"]} for r in rows]

    def add_audit(self, conversation_id: str, owner: str, event_type: str, payload: dict[str, Any]) -> None:
        aid = str(uuid.uuid4())
        now = int(time.time())
        with self.tx() as con:
            con.execute(
                "INSERT INTO audits (id, conversation_id, owner, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (aid, conversation_id, owner, event_type, json.dumps(payload, ensure_ascii=False), now),
            )

    def add_pending_action(
        self,
        conversation_id: str,
        owner: str,
        tool_name: str,
        tool_args: dict[str, Any],
        destination: str,
        transport: str,
        ttl_seconds: int,
    ) -> PendingAction:
        pid = str(uuid.uuid4())
        now = int(time.time())
        expires_at = now + ttl_seconds
        nonce = str(uuid.uuid4())
        args_json = json.dumps(tool_args, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        with self.tx() as con:
            con.execute(
                """
                INSERT INTO pending_actions (
                    id, conversation_id, owner, tool_name, tool_args_json, destination, transport,
                    nonce, status, expires_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (pid, conversation_id, owner, tool_name, args_json, destination, transport, nonce, expires_at, now),
            )
        return PendingAction(
            id=pid,
            conversation_id=conversation_id,
            owner=owner,
            tool_name=tool_name,
            tool_args_json=args_json,
            destination=destination,
            transport=transport,
            expires_at=expires_at,
            nonce=nonce,
        )

    def get_pending(self, action_id: str) -> PendingAction | None:
        row = self._conn.execute(
            """
            SELECT id, conversation_id, owner, tool_name, tool_args_json, destination, transport, expires_at, nonce
            FROM pending_actions
            WHERE id=? AND status='pending'
            """,
            (action_id,),
        ).fetchone()
        if not row:
            return None
        return PendingAction(**dict(row))

    def consume_pending(self, action_id: str, owner: str, conversation_id: str, nonce: str, decision: str) -> PendingAction:
        now = int(time.time())
        with self.tx() as con:
            row = con.execute(
                """
                SELECT id, conversation_id, owner, tool_name, tool_args_json, destination, transport, expires_at, nonce
                FROM pending_actions
                WHERE id=? AND status='pending'
                """,
                (action_id,),
            ).fetchone()
            if not row:
                raise PermissionError("Aktion wurde bereits verwendet oder existiert nicht")
            if row["owner"] != owner or row["conversation_id"] != conversation_id:
                raise PermissionError("Aktion gehört nicht zu Nutzer/Konversation")
            if row["nonce"] != nonce:
                raise PermissionError("Aktion stimmt nicht mit der gespeicherten Anforderung überein")
            if row["expires_at"] < now:
                con.execute(
                    "UPDATE pending_actions SET status='expired', consumed_at=? WHERE id=?",
                    (now, action_id),
                )
                raise TimeoutError("Aktion ist abgelaufen")
            if decision not in {"approved", "rejected"}:
                raise ValueError("Ungültige Entscheidung")
            con.execute(
                "UPDATE pending_actions SET status=?, consumed_at=? WHERE id=? AND status='pending'",
                (decision, now, action_id),
            )
            return PendingAction(**dict(row))
