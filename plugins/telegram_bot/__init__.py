"""telegram-bot — MCP server bridging a single-operator Telegram chat.

Layered like the other plugins: a pure, testable core (allowlist, ring buffer,
update normalization) + a thin live edge behind the `TelegramClient` boundary
(real impl wraps `python-telegram-bot`, lazily imported). The MCP server and
long-poll worker compose these.
"""
