"""MCP tool logic — pure given an injected TelegramClient + buffer + allowlist.

Inbound tools serve the ring buffer (which only ever holds allowlisted
messages — the worker filters on ingest). Outbound tools re-validate the
target chat_id against the allowlist on every call (spec).
"""

from __future__ import annotations

from typing import Any

from .client import TelegramClient
from .core import MessageBuffer, is_allowed


class TelegramTools:
    def __init__(self, buffer: MessageBuffer, client: TelegramClient, allowed: set[int]):
        self.buffer = buffer
        self.client = client
        self.allowed = allowed

    # ---- inbound ----

    def get_latest_messages(self, limit: int = 20) -> dict[str, Any]:
        return {"ok": True, "messages": [m.summary() for m in self.buffer.latest(limit)]}

    def _media(self, message_id: int, want_type: str) -> dict[str, Any]:
        msg = self.buffer.get(message_id)
        if msg is None:
            return {"ok": False, "error": "not_found", "detail": f"no message {message_id} in buffer"}
        if msg.type != want_type:
            return {"ok": False, "error": "wrong_type",
                    "detail": f"message {message_id} is {msg.type}, not {want_type}"}
        if not msg.file_id:
            return {"ok": False, "error": "no_file", "detail": "message has no downloadable file"}
        try:
            path = self.client.download(msg.file_id)
        except Exception as exc:  # noqa: BLE001 — live edge, surface structured
            return {"ok": False, "error": "download_failed", "detail": str(exc)[:200]}
        return {"ok": True, "message_id": message_id, "path": path, "msg": msg}

    def get_voice(self, message_id: int) -> dict[str, Any]:
        r = self._media(message_id, "voice")
        if not r["ok"]:
            return r
        m = r.pop("msg")
        return {"ok": True, "path": r["path"], "mime_type": m.mime_type,
                "duration_seconds": m.duration_seconds}

    def get_photo(self, message_id: int) -> dict[str, Any]:
        r = self._media(message_id, "photo")
        if not r["ok"]:
            return r
        r.pop("msg", None)
        return {"ok": True, "path": r["path"]}

    def get_document(self, message_id: int) -> dict[str, Any]:
        r = self._media(message_id, "document")
        if not r["ok"]:
            return r
        m = r.pop("msg")
        return {"ok": True, "path": r["path"], "file_name": m.file_name, "mime_type": m.mime_type}

    # ---- outbound (allowlist enforced on every call) ----

    def _check(self, chat_id: int) -> dict[str, Any] | None:
        if not is_allowed(chat_id, self.allowed):
            return {"ok": False, "error": "chat_not_allowed",
                    "detail": f"chat_id {chat_id} is not in TELEGRAM_ALLOWED_CHAT_IDS"}
        return None

    def send_text(self, chat_id: int, text: str) -> dict[str, Any]:
        if (err := self._check(chat_id)):
            return err
        try:
            self.client.send_text(chat_id, text)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": "send_failed", "detail": str(exc)[:200]}
        return {"ok": True, "sent_to": chat_id}

    def send_photo(self, chat_id: int, path: str, caption: str | None = None) -> dict[str, Any]:
        if (err := self._check(chat_id)):
            return err
        try:
            self.client.send_photo(chat_id, path, caption)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": "send_failed", "detail": str(exc)[:200]}
        return {"ok": True, "sent_to": chat_id}

    def send_document(self, chat_id: int, path: str, caption: str | None = None) -> dict[str, Any]:
        if (err := self._check(chat_id)):
            return err
        try:
            self.client.send_document(chat_id, path, caption)
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": "send_failed", "detail": str(exc)[:200]}
        return {"ok": True, "sent_to": chat_id}
