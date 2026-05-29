"""Real TelegramClient backed by python-telegram-bot (live edge — not unit-tested).

Imported lazily by client.build_real_client so the pure core/tools never
require python-telegram-bot.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from telegram import Bot  # noqa: F401 — import error surfaces as MissingDependency upstream


class PTBClient:
    def __init__(self, token: str):
        self._bot = Bot(token)

    def _run(self, coro):
        return asyncio.run(coro)

    def download(self, file_id: str) -> str:
        async def _dl() -> str:
            f = await self._bot.get_file(file_id)
            suffix = Path(f.file_path or "").suffix or ""
            fd, path = tempfile.mkstemp(prefix="hermes-tg-", suffix=suffix)
            Path(path).close() if hasattr(Path(path), "close") else None
            import os
            os.close(fd)
            await f.download_to_drive(path)
            return path
        return self._run(_dl())

    def send_text(self, chat_id: int, text: str) -> None:
        self._run(self._bot.send_message(chat_id=chat_id, text=text))

    def send_photo(self, chat_id: int, path: str, caption: str | None = None) -> None:
        async def _send() -> None:
            with open(path, "rb") as fh:
                await self._bot.send_photo(chat_id=chat_id, photo=fh, caption=caption)
        self._run(_send())

    def send_document(self, chat_id: int, path: str, caption: str | None = None) -> None:
        async def _send() -> None:
            with open(path, "rb") as fh:
                await self._bot.send_document(chat_id=chat_id, document=fh, caption=caption)
        self._run(_send())
