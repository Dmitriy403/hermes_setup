## Why

The user has invested significant effort curating a Claude Code ("Hermes agent") environment on this machine — custom skills, MCP servers, plugins, settings, hooks, keybindings, CLAUDE.md, and assorted tooling. Today, reproducing this setup on a new machine is a manual, error-prone exercise of copying files and re-installing dependencies one by one. We need a single installer that (a) captures the current state declaratively and (b) replays it on a fresh machine with one command, so the environment is portable and recoverable.

## What Changes

- Add a CLI installer (`hermes`) with three top-level commands: `capture`, `install`, `verify`.
- `hermes capture` snapshots the current machine's Claude Code configuration into a versioned, declarative manifest stored inside this repo (`hermes_setup`).
- `hermes install` reads the manifest on a target machine and reproduces the environment: installs Claude Code, restores `~/.claude/` config files, reinstalls plugins, registers MCP servers, wires hooks, and writes `CLAUDE.md`.
- `hermes verify` diffs the running machine against the manifest and reports drift (missing skills, extra plugins, settings divergence).
- Define a manifest format (`hermes.yaml` + per-component files under `manifest/`) that is human-readable and source-controllable.
- Provide a bootstrap script (`install.sh`) usable via `curl | sh` so a fresh machine can fetch the repo and run `hermes install` without any prerequisites beyond a POSIX shell.
- Secrets (API keys, OAuth tokens) are **never** captured into the manifest; the installer prompts for them or reads them from a separate, gitignored `secrets.env`.

## Capabilities

### New Capabilities

**Installer core:**
- `manifest`: declarative description of a Hermes/Claude Code environment (skills, plugins, MCP servers, settings, hooks, CLAUDE.md, keybindings, custom commands).
- `capture`: scan the current machine and write a manifest that fully describes its Claude Code configuration, excluding secrets and ephemeral state.
- `install`: read a manifest on a target machine and reproduce the described environment idempotently.
- `verify`: compare a running machine against a manifest and report drift with actionable diffs.
- `bootstrap`: one-shot entrypoint (`install.sh`) that installs prerequisites and runs `hermes install` on a fresh machine.

**Bundled agent plugins** — scope split per design.md Decision 19 (2026-05-28). This change (v0.1.0) ships the two plugins that prove both install paths (a skill and an MCP server) and are fully verifiable on this machine. The three dependency-heavy plugins move to a follow-on change `hermes-bundled-agent-plugins` (v0.2.0), because their live edges (Telegram API, `whisper.cpp`, `restic`) cannot be tested here and they are forward-looking *additions* to the agent rather than part of making the *existing* environment portable.

v0.1.0 (this change):
- `plugin-vision`: image-recognition pipeline (description / OCR / structured extraction) delivered as a Claude Code skill using Claude's native vision; no separate model.
- `plugin-macos-control`: macOS automation MCP server (focus/list windows, screenshots, type text, key combos, AppleScript, notifications) via `osascript` and `screencapture`.

v0.2.0 (follow-on change `hermes-bundled-agent-plugins`):
- `plugin-telegram-bot`: Telegram bot bridge MCP server (receive messages/photos/voice/documents, send replies) with a single-operator chat-ID allowlist.
- `plugin-voice`: speech-to-text (Telegram voice notes, `.m4a`/`.ogg`/`.wav`) — local `whisper.cpp` default, optional cloud Whisper fallback gated by a secret.
- `plugin-backups`: scheduled `restic` backups (via `launchd`) of a user-declared path set to a local/external/`rclone` destination.

### Modified Capabilities
<!-- None — this is a greenfield project. -->

The v0.1.0 plugins are part of the manifest and reproducible via `hermes install`. The v0.2.0 plugins will be added to the manifest by the follow-on change; the installer needs no new mechanics to carry them.

### Modified Capabilities
<!-- None — this is a greenfield project. -->

## Impact

- **New code**: a `hermes` CLI (Python 3.11+), a manifest schema, capture/install/verify modules, `install.sh`, and five bundled-plugin MCP servers under `plugins/<name>/` in this repo.
- **New files in repo**: `manifest/hermes.yaml`, `manifest/skills/`, `manifest/plugins/`, `manifest/mcp/`, `manifest/settings/`, `manifest/hooks/`, the CLI source, plus `plugins/telegram_bot/`, `plugins/vision/`, `plugins/macos_control/`, `plugins/voice/`, `plugins/backups/`.
- **No changes to existing code**: `hermes_setup/` is currently empty apart from `openspec/` and `.claude/`, so there is nothing to migrate.
- **External dependencies**:
  - Installer core: `claude` CLI, `git`, Python 3.11+, `pyyaml`.
  - Plugin runtimes: `python-telegram-bot` (telegram bot), `whisper.cpp` (voice, local default), `restic` + `rclone` (backups), `osascript` & `screencapture` (macOS control — built-in).
  - The bootstrap script installs any of the above that are missing on first run.
- **Privacy/security**: the installer must explicitly exclude `~/.claude/{projects,sessions,history.jsonl,todos,telemetry,debug,cache,paste-cache,backups,file-history,shell-snapshots,mcp-needs-auth-cache.json,vscode-claude-status-cache.json,settings.local.json}`. Telegram bot token, allowlisted chat IDs, and any cloud-backup credentials live in `secrets.env` only — never in the manifest. The macOS control plugin requires the user to grant Accessibility/Screen Recording permissions to the host shell; this is documented in README.
