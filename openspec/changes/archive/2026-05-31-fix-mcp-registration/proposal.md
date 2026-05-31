## Why

`hermes install` registers MCP servers by writing them into `~/.claude/settings.json`'s `mcpServers` map (v1 decision, to avoid depending on `claude mcp add`). But Claude Code does **not** read MCP servers from `settings.json` — it reads `~/.claude.json` (managed by `claude mcp add`) and project `.mcp.json`. As a result every MCP server hermes "installs" (telegram-bot, macos-control, voice) silently never loads, while `hermes verify` reports them as healthy because it only checks that the plugin package is present — not that Claude Code actually connects to the server. This was confirmed live this session: `claude mcp list` showed none of the hermes MCP servers; `claude mcp add -s local telegram-bot ...` made it `✓ Connected` immediately.

## What Changes

- **BREAKING (internal):** Stop writing MCP servers into `settings.json`'s `mcpServers` map. Register them through a config location Claude Code actually loads (`claude mcp add` → `~/.claude.json`, or a generated `.mcp.json`).
- `hermes install` registers each manifest MCP server via the supported mechanism, idempotently, honoring `--dry-run` and `--confirm`.
- On install, existing dead `mcpServers` entries previously written into `settings.json` are detected and removed (migration), so the two configs don't drift or double-register.
- `hermes verify` gains a real "is this MCP server loadable by Claude Code" check (distinct from "plugin package present"), so a declared-but-unloaded server is reported as drift instead of `match`.
- A regression test reproduces the original bug class: a manifest MCP server must end up in a location Claude Code reads, and must NOT be considered registered merely because it sits in `settings.json`.

## Capabilities

### New Capabilities
- `mcp-registration`: How hermes registers manifest-declared MCP servers so Claude Code actually loads them — the config location, idempotency, scope, dry-run/confirm behavior, migration away from `settings.json`, and what `verify` must assert.

### Modified Capabilities
<!-- No existing specs in openspec/specs/ yet; nothing to modify. -->

## Impact

- **Code:**
  - `src/hermes/install/installer.py` — `_build_settings` (drops `mcpServers` injection, ~lines 219-224) and `step_files` / a new MCP-registration step.
  - `src/hermes/verify.py` — `_verify_settings` (no longer expects `mcpServers`) and a new MCP-load verifier alongside `_verify_plugin_packages`.
  - Possibly `src/hermes/plugins_registry.py` for the registered-server list.
- **Behavior:** Fresh `hermes install` will, for the first time, make macos-control / voice / telegram-bot actually load in Claude Code.
- **Migration:** Machines already installed carry stale `mcpServers` in `settings.json`; install must clean them up. The Layer A hooks (PreToolUse/SessionStart/Stop) in `settings.json` must be left untouched.
- **Dependency:** Introduces a dependency on the `claude` CLI being present for MCP registration (the v1 decision explicitly tried to avoid this) — design must cover the fallback when `claude` is absent.
- **Docs/Decisions:** Reverses the installer docstring decision ("MCP servers are written into settings.json's mcpServers map for v1").
