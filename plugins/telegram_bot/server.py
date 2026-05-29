"""telegram-bot MCP server.

Validates config (fail-fast on missing/empty allowlist), starts the long-poll
worker in a background thread feeding a shared buffer, and exposes inbound +
outbound MCP tools. `mcp` and `python-telegram-bot` are imported lazily.
"""

from __future__ import annotations

import os
import sys
import threading

from .client import MissingDependency, build_real_client
from .core import MessageBuffer, ConfigError, parse_allowlist, validate_config
from .tools import TelegramTools
from .worker import run_worker


def main() -> int:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    allowed = parse_allowlist(os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS"))
    try:
        validate_config(token, allowed)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        client = build_real_client(token)
    except MissingDependency as exc:
        print(str(exc), file=sys.stderr)
        return 1

    buffer = MessageBuffer()
    threading.Thread(target=run_worker, args=(token, allowed, buffer), daemon=True).start()

    from mcp.server.fastmcp import FastMCP

    tools = TelegramTools(buffer, client, allowed)
    server = FastMCP("telegram-bot")

    @server.tool()
    def tg_get_latest_messages(limit: int = 20) -> dict:
        """Recent allowlisted messages: sender, timestamp, type, content."""
        return tools.get_latest_messages(limit)

    @server.tool()
    def tg_get_voice(message_id: int) -> dict:
        """Download a voice note; returns {path, mime_type, duration_seconds}."""
        return tools.get_voice(message_id)

    @server.tool()
    def tg_get_photo(message_id: int) -> dict:
        """Download a photo; returns {path}."""
        return tools.get_photo(message_id)

    @server.tool()
    def tg_get_document(message_id: int) -> dict:
        """Download a document; returns {path, file_name}."""
        return tools.get_document(message_id)

    @server.tool()
    def tg_send_text(chat_id: int, text: str) -> dict:
        """Send a text reply (chat_id must be allowlisted)."""
        return tools.send_text(chat_id, text)

    @server.tool()
    def tg_send_photo(chat_id: int, path: str, caption: str | None = None) -> dict:
        """Send an image file (chat_id must be allowlisted)."""
        return tools.send_photo(chat_id, path, caption)

    @server.tool()
    def tg_send_document(chat_id: int, path: str, caption: str | None = None) -> dict:
        """Send any file (chat_id must be allowlisted)."""
        return tools.send_document(chat_id, path, caption)

    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
