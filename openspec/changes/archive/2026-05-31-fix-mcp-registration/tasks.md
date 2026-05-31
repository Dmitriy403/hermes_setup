## 1. MCP CLI adapter

- [x] 1.1 Add a small `mcp_cli` adapter module wrapping `claude mcp add / get / list / remove`, with `which("claude")` detection and structured results (registered names, errors). Keep all `claude mcp` calls isolated here.
- [x] 1.2 Unit-test the adapter against a faked `claude` binary (subprocess stub): add, idempotent re-add (skip), get-missing, list parsing, remove, and CLI-absent path.

## 2. Installer: register MCP via the supported path

- [x] 2.1 Remove the `mcpServers` injection from `_build_settings` (installer.py ~219-224); `_build_settings` must no longer add `mcpServers` to settings.json.
- [x] 2.2 Add a `step_mcp` install step that registers each manifest MCP server via the adapter at default scope `local`, idempotently (query-before-add), routed through the `Mutator` so `--dry-run` logs and `--confirm` prompts.
- [x] 2.3 Fail-soft when `claude` CLI is absent: skip registration, surface the unregistered server names plus the exact `claude mcp add` command(s) to run manually, and continue the rest of the install.
- [x] 2.4 Allow the manifest to override scope per server (default `local`); thread it into the adapter call.

## 3. Migration: strip dead settings.json mcpServers

- [x] 3.1 On install, detect a pre-existing `mcpServers` map in `settings.json` and remove entries whose names match manifest-declared servers (leave foreign keys and all Layer A hook keys untouched), via the `Mutator` (diff under `--confirm`, log under `--dry-run`).
- [x] 3.2 Verify the migration preserves `PreToolUse` / `SessionStart` / `Stop` hook blocks byte-for-byte.

## 4. verify: real MCP-load check

- [x] 4.1 Update `_verify_settings` to stop expecting `mcpServers` in the rebuilt settings (so a clean settings.json is `match`).
- [x] 4.2 Add an MCP-registration verifier: for each manifest server, report drift when it is absent from a Claude-Code-read location (`~/.claude.json` / `.mcp.json`); a server present only under `settings.json.mcpServers` counts as NOT registered. Decide presence-check vs `--probe` per design.
- [x] 4.3 Ensure `_verify_plugin_packages` no longer implies a server is loadable (separate "package present" from "registered with CC").

## 5. Regression test (the bug class)

- [x] 5.1 Add a test asserting that after install, a manifest MCP server lands in a Claude-Code-read location and that `settings.json` contains no `mcpServers` key.
- [x] 5.2 Add a test asserting `hermes verify` flags a server that exists only in `settings.json.mcpServers` as drift (not `match`).

## 6. Docs & decisions

- [x] 6.1 Update the installer module docstring (reverse the "MCP servers are written into settings.json for v1" decision) and any README/CHANGELOG notes.
- [x] 6.2 Run the full test suite and `hermes verify` on this machine; confirm `macos-control` / `voice` / `telegram-bot` register (or fail-soft cleanly) and that the green-while-dead state is gone.
