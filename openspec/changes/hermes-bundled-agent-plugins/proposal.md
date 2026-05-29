## Why

`hermes-agent-installer` (v0.1.0) shipped the installer core, the four-layer security model, and two bundled plugins (`vision`, `macos-control`). Three further plugins — `telegram-bot`, `voice`, `backups` — were split out of that change (design Decision 19) because their live edges (the Telegram Bot API, `whisper.cpp`/`ffmpeg`, `restic`) cannot be verified on a machine without those dependencies, and they are forward-looking *additions* to the agent rather than part of making the existing environment portable. This change delivers those three plugins on top of the now-stable installer + manifest + security framework.

## What Changes

- Add `plugins/telegram_bot/` — a Telegram bot bridge MCP server (long-poll, single-operator chat-ID allowlist) that lets the agent receive messages/photos/voice/documents and send replies.
- Add `plugins/voice/` — a transcription MCP server (`whisper.cpp` default, optional cloud Whisper fallback gated by a secret).
- Add `plugins/backups/` — `restic`-based scheduled snapshots (via `launchd`) of a user-declared path set to a local/external/`rclone` destination, with failure alerts.
- Register the three as MCP servers / manifest entries so `hermes install` carries them. No new installer mechanics are required (the v0.1.0 install path already handles MCP servers and plugins).

## Capabilities

### New Capabilities

- `plugin-telegram-bot`: inbound/outbound Telegram MCP tools, chat-ID allowlist enforcement, in-memory ring buffer, launchd supervision.
- `plugin-voice`: `voice.transcribe(path, language?)` with local-default backend and opt-in cloud fallback (privacy default: no audio leaves the machine).
- `plugin-backups`: declarative `manifest/backups.yaml`, `hermes-backup` CLI (backup/verify/restore), launchd scheduling, and failure notification via `macos-control` + Telegram.

### Modified Capabilities
<!-- None — these are additive plugins on top of the v0.1.0 framework. -->

## Impact

- **New code**: three plugin packages under `plugins/` (each its own `pyproject.toml`), their `manifest/mcp/*.yaml` entries, and a `manifest/backups.yaml`.
- **External dependencies** (installed lazily per design Decision 18, with fail-soft `missing_dependency` errors): `python-telegram-bot`, `whisper-cpp`, `ffmpeg`, `restic`, `rclone`.
- **Testing**: pure cores (allowlist, ring buffer, backend selection, restic argv, exclude lists, plist generation) are unit-tested; live round-trips (real Telegram/whisper/restic) are verified on a machine with the dependencies, per Decision 18.
- **Inherits** the v0.1.0 framework unchanged: manifest schema, `hermes install`/`verify`, the security model, and the two-repo (`hermes_setup` tool / `hermes_config` config) split.
