from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class TelegramDecision:
    allowed: bool
    reason: str = ""


class TelegramPolicy:
    def __init__(self, allowed_user_ids: tuple[int, ...]) -> None:
        self.allowed_user_ids = set(allowed_user_ids)

    def verify_private_chat(self, update: dict[str, Any]) -> TelegramDecision:
        message = update.get("message") or update.get("callback_query", {}).get("message") or {}
        chat = message.get("chat", {})
        if chat.get("type") != "private":
            return TelegramDecision(False, "Nur private Chats sind erlaubt")
        sender = (update.get("message") or {}).get("from") or (update.get("callback_query") or {}).get("from") or {}
        sender_id = sender.get("id")
        if sender_id is None or sender_id not in self.allowed_user_ids:
            return TelegramDecision(False, "Benutzer nicht erlaubt")
        if update.get("callback_query"):
            if chat.get("id") != sender_id:
                return TelegramDecision(False, "Callback gehört nicht zum Benutzer")
        return TelegramDecision(True)
