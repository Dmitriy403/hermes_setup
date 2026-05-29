"""The live boundary — a `TelegramClient` protocol the tools depend on.

Tests inject a fake; the real implementation wraps `python-telegram-bot`
(lazily imported, so core/tools import without it — Decision 18 fail-soft).
"""

from __future__ import annotations

from typing import Protocol


class TelegramClient(Protocol):
    def download(self, file_id: str) -> str:
        """Download a Telegram file to a local temp path; return the path."""
        ...

    def send_text(self, chat_id: int, text: str) -> None: ...
    def send_photo(self, chat_id: int, path: str, caption: str | None = None) -> None: ...
    def send_document(self, chat_id: int, path: str, caption: str | None = None) -> None: ...


def build_real_client(token: str) -> TelegramClient:
    """Construct the python-telegram-bot-backed client, or fail soft."""
    try:
        from .ptb_client import PTBClient  # noqa: WPS433
    except ImportError as exc:  # python-telegram-bot not installed
        raise MissingDependency(
            "python-telegram-bot is not installed; run `pip install python-telegram-bot` "
            "(or reinstall the telegram_bot plugin)."
        ) from exc
    return PTBClient(token)


class MissingDependency(Exception):
    """Raised when the live client's dependency (python-telegram-bot) is absent."""
