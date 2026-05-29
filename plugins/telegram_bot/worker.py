"""Long-poll worker — ingests allowlisted Telegram updates into a buffer.

Live edge: lazily uses python-telegram-bot. Filters on the allowlist BEFORE
normalizing/storing, so the buffer only ever holds allowlisted messages.
Run standalone via launchd (`python -m telegram_bot.worker`) or as a thread
inside the MCP server.
"""

from __future__ import annotations

import os
import sys

from .core import MessageBuffer, is_allowed, normalize_update, parse_allowlist, validate_config


def run_worker(token: str, allowed: set[int], buffer: MessageBuffer) -> None:
    import asyncio

    from telegram import Bot

    async def loop() -> None:
        bot = Bot(token)
        offset: int | None = None
        while True:
            updates = await bot.get_updates(offset=offset, timeout=30)
            for u in updates:
                offset = u.update_id + 1
                d = u.to_dict()
                msg_d = d.get("message") or d.get("channel_post") or {}
                chat_id = (msg_d.get("chat") or {}).get("id")
                if chat_id is None or not is_allowed(chat_id, allowed):
                    sys.stderr.write(f"telegram-bot: rejected message from chat {chat_id} (not allowlisted)\n")
                    continue
                m = normalize_update(d)
                if m is not None:
                    buffer.add(m)

    asyncio.run(loop())


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    allowed = parse_allowlist(os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS"))
    try:
        validate_config(token, allowed)
    except Exception as exc:  # ConfigError
        print(str(exc), file=sys.stderr)
        return 1
    run_worker(token, allowed, MessageBuffer())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
