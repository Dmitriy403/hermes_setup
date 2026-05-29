## ADDED Requirements

### Requirement: Telegram bot is shipped as an MCP server bundled with the installer
The repo SHALL contain a `plugins/telegram_bot/` package that exposes an MCP server named `telegram-bot`. The manifest SHALL register this server so that `hermes install` makes its tools available to Claude Code on the target machine.

#### Scenario: After install, the telegram-bot MCP server is reachable
- **WHEN** `hermes install` has completed on a machine
- **AND** `claude mcp list` is invoked
- **THEN** the `telegram-bot` server is listed and its status is "connected"

### Requirement: Bot is restricted to an explicit chat-ID allowlist
The bot MUST reject every incoming message whose `chat.id` is not in the `TELEGRAM_ALLOWED_CHAT_IDS` allowlist (comma-separated env var, sourced from `secrets.env`). The allowlist MUST contain at least one ID — empty/missing means the bot SHALL refuse to start.

#### Scenario: Message from unknown chat is ignored
- **WHEN** a Telegram message arrives from a chat ID not in `TELEGRAM_ALLOWED_CHAT_IDS`
- **THEN** the bot logs the rejection and does not forward the message to Claude
- **AND** does not reply to the sender

#### Scenario: Missing allowlist prevents startup
- **WHEN** the bot process starts with `TELEGRAM_ALLOWED_CHAT_IDS` unset or empty
- **THEN** it exits non-zero with an error message naming the missing variable

### Requirement: Bot exposes inbound MCP tools
The `telegram-bot` MCP server SHALL expose at least:
- `tg_get_latest_messages(limit)`: returns recent allowlisted messages with sender, timestamp, type, and content.
- `tg_get_voice(message_id)`: returns the path to a downloaded voice/audio file for transcription.
- `tg_get_photo(message_id)`: returns the path to a downloaded photo for vision analysis.
- `tg_get_document(message_id)`: returns the path to a downloaded file.

#### Scenario: Voice note downloaded on demand
- **WHEN** Claude calls `tg_get_voice(message_id=42)` for an allowlisted voice note
- **THEN** the file is downloaded to a temp path
- **AND** the tool returns `{path, mime_type, duration_seconds}`

### Requirement: Bot exposes outbound MCP tools
The server SHALL expose at least:
- `tg_send_text(chat_id, text)`: send a text reply.
- `tg_send_photo(chat_id, path, caption?)`: send an image file.
- `tg_send_document(chat_id, path, caption?)`: send any file.

`chat_id` MUST be validated against the allowlist on every call.

#### Scenario: Outbound send to non-allowlisted chat is refused
- **WHEN** Claude calls `tg_send_text(chat_id=999, text="…")` and `999` is not allowlisted
- **THEN** the tool returns an error and does not send
