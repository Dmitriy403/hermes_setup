# Tasks — hermes-bundled-agent-plugins (v0.2.0)
<!-- Deferred from hermes-agent-installer per Decision 19. Specs inherited
unchanged: specs/plugin-telegram-bot, plugin-voice, plugin-backups.
Build telegram-bot first (keystone); follow the pure-core + injected-boundary
pattern and Decision 18 (fail-soft + lazy deps). -->

## 1. Plugin: telegram-bot

- [ ] 1.1 Create `plugins/telegram_bot/` Python package with `pyproject.toml` depending on `python-telegram-bot`, `mcp` (Anthropic MCP SDK).
- [ ] 1.2 Implement long-polling worker that reads `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_CHAT_IDS` from env; exit fast on missing/empty allowlist.
- [ ] 1.3 Implement in-memory ring buffer of last N (configurable, default 200) allowlisted messages; metadata + cached file paths for media.
- [ ] 1.4 Implement inbound MCP tools: `tg_get_latest_messages`, `tg_get_voice`, `tg_get_photo`, `tg_get_document`. All tool responses validated against the allowlist.
- [ ] 1.5 Implement outbound MCP tools: `tg_send_text`, `tg_send_photo`, `tg_send_document`. Allowlist check on every `chat_id`.
- [ ] 1.6 Generate `launchd` plist `com.hermes.telegram-bot.plist` so the worker runs at login and restarts on crash; install via `hermes install`.
- [ ] 1.7 Manifest entry: add `manifest/mcp/telegram-bot.yaml` referencing the local package and declaring required env vars (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_IDS`).
- [ ] 1.8 Integration test with python-telegram-bot's fake-bot harness or a recorded fixture: allowlisted message arrives → MCP tool returns it; non-allowlisted message arrives → not visible to MCP. Pure-core unit tests: allowlist (in/out), empty-allowlist refusal, ring buffer eviction, update→message normalization (text/voice/photo/document).

## 2. Plugin: voice

- [ ] 2.1 Create `plugins/voice/` Python package + MCP server.
- [ ] 2.2 Add `whisper.cpp` as a dependency — first attempt `brew install whisper-cpp`; document the chosen path (per Decision 11). Fail soft with `missing_dependency` when absent (Decision 18).
- [ ] 2.3 Implement local-backend transcription: convert input to 16kHz mono WAV via `ffmpeg`, invoke `whisper-cpp`, parse JSON output.
- [ ] 2.4 Implement model auto-download to `~/.cache/hermes/whisper/`; default model `base`, configurable via `VOICE_WHISPER_MODEL`.
- [ ] 2.5 Implement optional cloud Whisper backend (OpenAI API) gated by `VOICE_CLOUD_MODE` and `OPENAI_API_KEY`; selection logic per spec. Unit-test the privacy guarantee: `VOICE_CLOUD_MODE=off ⇒ cloud backend never constructed / no network.
- [ ] 2.6 Implement `voice.transcribe(path, language?)` MCP tool; return `{text, language, duration_seconds, backend}`.
- [ ] 2.7 Manifest entry: `manifest/mcp/voice.yaml`.
- [ ] 2.8 Integration test with a 5-second fixture voice note (Russian and English variants).

## 3. Plugin: backups

- [ ] 3.1 Create `plugins/backups/` package with a `hermes-backup` console-script entrypoint.
- [ ] 3.2 Define `manifest/backups.yaml` schema: `sources` (paths + per-path excludes), `destination` (kind + per-kind config), `schedule` (interval).
- [ ] 3.3 Author the default `manifest/backups.yaml` covering `~/.hermes_setup/`, `~/.claude/` (with ephemeral exclusions), `~/Documents/`, and `$BACKUP_SECRETS_PATH`.
- [ ] 3.4 Implement `hermes-backup` to translate the manifest into a `restic backup` invocation per source, with merged exclude patterns; support `--dry-run`. Fail soft with `missing_dependency` when `restic` absent.
- [ ] 3.5 Implement `hermes-backup verify` (wraps `restic check`) and `hermes-backup restore --target=… [--path=…] [--snapshot=…]`.
- [ ] 3.6 Generate `~/Library/LaunchAgents/com.hermes.backup.plist` from `schedule`; install/load it during `hermes install`.
- [ ] 3.7 Implement failure notifier: on non-zero exit, send macOS notification AND, if `BACKUP_ALERT_CHAT_ID` and the `telegram-bot` MCP server are available, post a Telegram message with the stderr tail.
- [ ] 3.8 Manifest integration: capture/install reuse the same `manifest/backups.yaml`; verify reports drift if scheduled plist is missing or sources differ.
- [ ] 3.9 End-to-end test: write fixture data → backup to a `local:` destination in tmpdir → restore to another tmpdir → assert byte-identical files. (restic must be installed on the test machine.)

## 4. Cross-plugin + seed

- [ ] 4.1 Re-introduce `restic init` for the user's real destination (was §12.5 in the parent), once the backups plugin lands.
- [ ] 4.2 Add `telegram-bot`, `voice`, `backups` to the user's `hermes_config` manifest and `secrets.env` (TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_CHAT_IDS, optional OPENAI_API_KEY, backup destination creds, BACKUP_ALERT_CHAT_ID).
- [ ] 4.3 Document each plugin in `plugins/<name>/README.md` (what it does, env vars, required permissions, smoke-test commands).
