"""Pure core for telegram-bot — no `python-telegram-bot`, no network.

Holds the security boundary (chat-ID allowlist) and the data plumbing
(message normalization + ring buffer) that must not break. Fully unit-testable.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class ConfigError(Exception):
    """Raised when required Telegram config is missing/invalid."""


@dataclass
class Message:
    message_id: int
    chat_id: int
    sender: str
    timestamp: str            # ISO-8601
    type: str                 # text | voice | photo | document
    content: str              # text body, or a short descriptor for media
    file_id: str | None = None        # Telegram file id for media (download on demand)
    mime_type: str | None = None
    duration_seconds: int | None = None
    file_name: str | None = None

    def summary(self) -> dict[str, Any]:
        """The shape returned by tg_get_latest_messages."""
        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "timestamp": self.timestamp,
            "type": self.type,
            "content": self.content,
        }


# ---- allowlist (the security boundary) ----


def parse_allowlist(value: str | None) -> set[int]:
    """Parse a comma-separated TELEGRAM_ALLOWED_CHAT_IDS string into ints."""
    if not value:
        return set()
    out: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            continue
    return out


def validate_config(token: str | None, allowlist: set[int]) -> None:
    """Refuse to start on missing token or empty allowlist (spec)."""
    missing = []
    if not token:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not allowlist:
        missing.append("TELEGRAM_ALLOWED_CHAT_IDS (must contain at least one chat id)")
    if missing:
        raise ConfigError("telegram-bot cannot start — missing/empty: " + ", ".join(missing))


def is_allowed(chat_id: int, allowlist: set[int]) -> bool:
    return chat_id in allowlist


# ---- ring buffer ----


@dataclass
class MessageBuffer:
    maxlen: int = 200
    _buf: deque[Message] = field(default_factory=lambda: deque(maxlen=200))
    _index: dict[int, Message] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self._buf.maxlen != self.maxlen:
            self._buf = deque(self._buf, maxlen=self.maxlen)

    def add(self, msg: Message) -> None:
        if len(self._buf) == self._buf.maxlen and self._buf:
            evicted = self._buf[0]
            self._index.pop(evicted.message_id, None)
        self._buf.append(msg)
        self._index[msg.message_id] = msg

    def latest(self, limit: int = 20) -> list[Message]:
        if limit <= 0:
            return []
        return list(self._buf)[-limit:][::-1]  # newest first

    def get(self, message_id: int) -> Message | None:
        return self._index.get(message_id)

    def __len__(self) -> int:
        return len(self._buf)


# ---- update normalization ----


def _iso(epoch: Any) -> str:
    try:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OSError):
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_update(update: dict[str, Any]) -> Message | None:
    """Turn a Telegram update dict into a Message, or None if not a message
    we handle. Does NOT enforce the allowlist — the caller does that first."""
    msg = update.get("message") or update.get("channel_post")
    if not isinstance(msg, dict):
        return None
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return None
    frm = msg.get("from") or {}
    sender = frm.get("username") or frm.get("first_name") or str(frm.get("id", "?"))
    ts = _iso(msg.get("date"))
    mid = msg.get("message_id", 0)

    if "text" in msg:
        return Message(mid, chat_id, sender, ts, "text", msg["text"])
    if "voice" in msg:
        v = msg["voice"]
        return Message(mid, chat_id, sender, ts, "voice", "[voice note]",
                       file_id=v.get("file_id"), mime_type=v.get("mime_type"),
                       duration_seconds=v.get("duration"))
    if "photo" in msg:
        photos = msg["photo"] or []
        largest = photos[-1] if photos else {}
        return Message(mid, chat_id, sender, ts, "photo", "[photo]",
                       file_id=largest.get("file_id"))
    if "document" in msg:
        d = msg["document"]
        return Message(mid, chat_id, sender, ts, "document",
                       f"[document: {d.get('file_name', 'file')}]",
                       file_id=d.get("file_id"), mime_type=d.get("mime_type"),
                       file_name=d.get("file_name"))
    return None
