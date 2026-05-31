# Changelog

All notable changes to `hermes_setup` are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/); versions are the
public tool's releases.

## [0.1.0] — unreleased

First release: the reusable **tool** that captures, installs, and verifies a
Claude Code ("Hermes agent") environment, with a four-layer security model.
Personal configuration is kept in a separate private repo (`hermes_config`);
this repo is the public tool only (design Decision 20).

### Installer core
- `hermes capture` — snapshot `~/.claude` into a manifest (skills, plugins,
  MCP servers, settings, hooks, CLAUDE.md, keybindings), excluding ephemerals
  and redacting secrets to `${VAR}` placeholders + `secrets.env.example`.
- `hermes install` — replay a manifest onto a target machine: fail-fast on
  missing secrets, idempotent, staging + atomic writes, `--dry-run`.
- `hermes verify` — diff machine vs manifest (match / missing / extra /
  modified), structural settings diff, probe cdhash check, `--json`.
- Manifest schema v1 (typed, lossless round-trip) with env-var resolution.
- Two-repo model: `--manifest-dir` / `HERMES_MANIFEST_DIR` decouple the config
  repo from the tool; `$HOME` paths are templated on capture and expanded on
  install for cross-machine portability.
- MCP servers are registered via `claude mcp add` (the location Claude Code
  actually loads: `~/.claude.json` / `.mcp.json`), **not** written into
  `settings.json`'s `mcpServers` map — which Claude Code ignores, so the old v1
  approach left every server dead. Non-polling servers default to `user` scope
  (available everywhere); polling servers (e.g. `telegram-bot`) set
  `scope: local` in their manifest sidecar to avoid a Telegram `getUpdates` 409
  from multiple concurrent pollers. Per-server `scope` override; idempotent;
  fail-soft (surfaces the manual `claude mcp add` command) when `claude` is
  absent; install strips any stale `mcpServers` left in `settings.json`.
  `hermes verify` now reports an MCP server that is declared but not registered
  with Claude Code (e.g. present only under `settings.json`) as drift, instead
  of `match` based on plugin-package presence alone.

### Security
- `hermes capabilities` — show the effective Layer A policy.
- **Layer A** (always on): a `PreToolUse` hook enforces `permissions.yaml`
  (filesystem forbidden paths, shell deny/ask, network domains, MCP gating)
  before a tool call reaches the OS.
- **Layer B** (opt-in): `hermes run` launches Claude under `sandbox-exec` with
  a profile generated from `permissions.yaml`; `hermes doctor` diagnoses gaps.
- `hermes doctor` — read-only macOS TCC checkup: three-axis classifier
  (rebuild / terminal-swap / revoke), 2×2 sandbox×TCC matrix, deep-link fixes,
  `--fix` / `--reset` / `--mdm-profile` / `--suggest-sandbox-patch` /
  `--plugin-deps`.
- `bin/hermes-probe-tcc` — ad-hoc-signed Swift TCC probe (silent preflight
  APIs, responsible-process detection, `--self-test` sandbox mode).

### Bundled plugins
- `vision` — image describe / OCR / extract via Claude's native vision (skill).
- `macos-control` — windows, screenshots, input, AppleScript, notifications
  (MCP server) with structured TCC-permission errors.

### Bootstrap & docs
- `install.sh` — `curl | bash` bootstrap (prereqs via Homebrew, pipx install,
  clone, hand off to `hermes install`).
- `README.md`, `SECURITY.md`, per-plugin docs.

### Deferred to 0.2.0 (`hermes-bundled-agent-plugins`)
- `telegram-bot`, `voice`, `backups` — split out per design Decision 19
  (dependency-heavy, verified on a real-deps machine).

### Notes
- `git tag v0.1.0` is a manual step once the repo is initialized and the §6.5
  clean-VM smoke test passes.
