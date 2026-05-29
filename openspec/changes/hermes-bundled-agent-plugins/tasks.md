# Tasks — hermes-bundled-agent-plugins (v0.2.0)
<!-- Deferred from hermes-agent-installer per Decision 19. Specs inherited
unchanged: specs/plugin-telegram-bot, plugin-voice, plugin-backups.
Build telegram-bot first (keystone); follow the pure-core + injected-boundary
pattern and Decision 18 (fail-soft + lazy deps). -->

## 1. Plugin: telegram-bot

- [x] 1.1 Create `plugins/telegram_bot/` Python package with `pyproject.toml` depending on `python-telegram-bot`, `mcp` (Anthropic MCP SDK).
- [x] 1.2 Implement long-polling worker that reads `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_CHAT_IDS` from env; exit fast on missing/empty allowlist.
- [x] 1.3 Implement in-memory ring buffer of last N (configurable, default 200) allowlisted messages; metadata + cached file paths for media.
- [x] 1.4 Implement inbound MCP tools: `tg_get_latest_messages`, `tg_get_voice`, `tg_get_photo`, `tg_get_document`. All tool responses validated against the allowlist.
- [x] 1.5 Implement outbound MCP tools: `tg_send_text`, `tg_send_photo`, `tg_send_document`. Allowlist check on every `chat_id`.
- [x] 1.6 Generate `launchd` plist `com.hermes.telegram-bot.plist` so the worker runs at login and restarts on crash; install via `hermes install`.
- [x] 1.7 Manifest entry: add `manifest/mcp/telegram-bot.yaml` referencing the local package and declaring required env vars (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_CHAT_IDS`).
- [x] 1.8 Integration test with python-telegram-bot's fake-bot harness or a recorded fixture: allowlisted message arrives → MCP tool returns it; non-allowlisted message arrives → not visible to MCP. Pure-core unit tests: allowlist (in/out), empty-allowlist refusal, ring buffer eviction, update→message normalization (text/voice/photo/document).

## 2. Plugin: voice

- [x] 2.1 Create `plugins/voice/` Python package + MCP server.
- [x] 2.2 Add `whisper.cpp` as a dependency — first attempt `brew install whisper-cpp`; document the chosen path (per Decision 11). Fail soft with `missing_dependency` when absent (Decision 18).
- [x] 2.3 Implement local-backend transcription: convert input to 16kHz mono WAV via `ffmpeg`, invoke `whisper-cpp`, parse JSON output.
- [x] 2.4 Implement model auto-download to `~/.cache/hermes/whisper/`; default model `base`, configurable via `VOICE_WHISPER_MODEL`. *(Done: `core.model_url` builds the validated HuggingFace URL (pure/tested); `backends.ensure_model` atomically downloads `ggml-<model>.bin` to ~/.cache/hermes/whisper on first transcription, fail-soft `missing_dependency` if the fetch fails. LocalWhisper now auto-downloads instead of erroring on absent model.)*
- [x] 2.5 Implement optional cloud Whisper backend (OpenAI API) gated by `VOICE_CLOUD_MODE` and `OPENAI_API_KEY`; selection logic per spec. Unit-test the privacy guarantee: `VOICE_CLOUD_MODE=off ⇒ cloud backend never constructed / no network.
- [x] 2.6 Implement `voice.transcribe(path, language?)` MCP tool; return `{text, language, duration_seconds, backend}`.
- [x] 2.7 Manifest entry: `manifest/mcp/voice.yaml`.
- [x] 2.8 Integration test with a 5-second fixture voice note (Russian and English variants). *(Pure core + orchestration tested: select matrix incl. cloud-off privacy, ffmpeg/whisper argv, whisper-json parse, backend fall-through, unsupported-format. Live whisper round-trip on a real fixture deferred per Decision 18.)*

## 3. Plugin: backups

- [x] 3.1 Create `plugins/backups/` package with a `hermes-backup` console-script entrypoint.
- [x] 3.2 Define `manifest/backups.yaml` schema: `sources` (paths + per-path excludes), `destination` (kind + per-kind config), `schedule` (interval).
- [x] 3.3 Author the default `manifest/backups.yaml` covering `~/.hermes_setup/`, `~/.claude/` (with ephemeral exclusions), `~/Documents/`, and `$BACKUP_SECRETS_PATH`.
- [x] 3.4 Implement `hermes-backup` to translate the manifest into a `restic backup` invocation per source, with merged exclude patterns; support `--dry-run`. Fail soft with `missing_dependency` when `restic` absent.
- [x] 3.5 Implement `hermes-backup verify` (wraps `restic check`) and `hermes-backup restore --target=… [--path=…] [--snapshot=…]`.
- [x] 3.6 Generate `~/Library/LaunchAgents/com.hermes.backup.plist` from `schedule`; install/load it during `hermes install`.
- [x] 3.7 Implement failure notifier: on non-zero exit, send macOS notification AND, if `BACKUP_ALERT_CHAT_ID` and the `telegram-bot` MCP server are available, post a Telegram message with the stderr tail.
- [x] 3.8 Manifest integration: capture/install reuse the same `manifest/backups.yaml`; verify reports drift if scheduled plist is missing or sources differ. *(Done: backups side (launchd plist + backups.yaml) + the `hermes verify` drift-check — §5.5 `_verify_launchd` flags a missing `com.hermes.backup` plist. Finer-grained 'sources differ' drift is a future nicety.)*
- [x] 3.9 End-to-end test: write fixture data → backup to a `local:` destination in tmpdir → restore to another tmpdir → assert byte-identical files. (restic must be installed on the test machine.) *(Done: `test_e2e_backup_restore_roundtrip` in tests/test_backups.py — restic 0.18.1 installed via brew; fixture → restic init → `hermes-backup backup` → `restore` → byte-identical assertion (incl. `node_modules` default-exclude held) → `verify` (restic check) clean. Skips itself when restic is absent. 12/12 backups tests pass.)*

## 4. Cross-plugin + seed

- [ ] 4.1 Re-introduce `restic init` for the user's real destination (was §12.5 in the parent), once the backups plugin lands. *(USER: real restic init at your chosen destination.)*
- [ ] 4.2 Add `telegram-bot`, `voice`, `backups` to the user's `hermes_config` manifest and `secrets.env` (TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_CHAT_IDS, optional OPENAI_API_KEY, backup destination creds, BACKUP_ALERT_CHAT_ID). *(USER: add the 3 plugins to ~/hermes_config manifest + secrets.env, then push.)*
- [x] 4.3 Document each plugin in `plugins/<name>/README.md` (what it does, env vars, required permissions, smoke-test commands).

## 5. Plugin install orchestration (form B — design.md "Decision: plugin install orchestration")

- [x] 5.1 Add a plugin registry in the tool (`src/hermes/plugins_registry.py`): name → {package dir, console-scripts, launchd label+generator, kind mcp|skill|cli}. Single source install/verify consult.
- [x] 5.2 `hermes install`: for each plugin the manifest registers (mcp command `hermes-*` resolved via the registry, or `manifest/backups.yaml` present), `pipx inject hermes <repo>/plugins/<dir>` (fallback `pip install`); idempotent + dry-run via Mutator. Skip already-injected.
- [x] 5.3 `hermes install`: for registered plugins with a launchd job, write `~/Library/LaunchAgents/<label>.plist` from the plugin's generator and `launchctl bootstrap gui/$UID` (or `load -w`); unload/remove when the plugin is no longer registered. Honor dry-run.
- [x] 5.4 Add `[project.optional-dependencies]` extras to the top-level `pyproject.toml` (`macos-control`, `telegram`, `voice`, `backups`, `all`) for dev installs (`pip install -e '.[telegram]'`).
- [x] 5.5 `hermes verify`: report a registered plugin whose console-script is missing from PATH, or whose launchd job is not loaded, as drift (closes §3.8 verify side).
- [x] 5.6 Tests: registry mapping; `pipx inject` argv per registered plugin (injected runner); launchd plist path + `launchctl` argv; verify-drift when a console-script/launchd job is absent.
- [x] 5.7 Backfill: ensure v0.1.0's `macos-control` is covered by the same orchestration (its mcp entry already points at `hermes-macos-control`). *(Done by construction: macos-control is in the registry as an installable mcp plugin, so step_plugin_packages injects it like the others.)*
