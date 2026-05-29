# telegram-bot

A single-operator Telegram bridge MCP server: the agent receives messages,
photos, voice notes, and documents from you, and sends replies back. Long-poll,
no public IP / webhook needed.

## Tools

| Tool | What it does |
|------|--------------|
| `tg_get_latest_messages(limit)` | recent allowlisted messages {sender, ts, type, content} |
| `tg_get_voice(message_id)` | download a voice note → {path, mime_type, duration_seconds} |
| `tg_get_photo(message_id)` | download a photo → {path} |
| `tg_get_document(message_id)` | download a file → {path, file_name} |
| `tg_send_text(chat_id, text)` | send a text reply |
| `tg_send_photo(chat_id, path, caption?)` | send an image |
| `tg_send_document(chat_id, path, caption?)` | send any file |

## Security — chat-ID allowlist

The bot **refuses to start** without `TELEGRAM_ALLOWED_CHAT_IDS` (≥1 id). Every
inbound message from a non-allowlisted chat is dropped (never reaches Claude),
and every outbound `chat_id` is re-validated against the allowlist on each call.

## Env (via secrets.env)

- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `TELEGRAM_ALLOWED_CHAT_IDS` — comma-separated chat ids (your own)

## Run

Registered as the `telegram-bot` MCP server (`manifest/mcp/telegram-bot.yaml`).
`hermes install` installs a launchd agent (`com.hermes.telegram-bot`) so the
long-poll worker runs at login and restarts on crash.

Requires `python-telegram-bot` (declared in this plugin's `pyproject.toml`).

## Smoke test

Message the bot from an allowlisted chat, then ask Claude to
`tg_get_latest_messages(5)` — your message should appear. A message from a
non-allowlisted chat must NOT appear.
