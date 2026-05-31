# mcp-registration

## Purpose

Ensure manifest-declared MCP servers are registered where Claude Code actually loads them, registration is idempotent and flag-aware, stale `settings.json` entries are migrated, the `claude` CLI's absence is handled gracefully, and `hermes verify` distinguishes "declared" from "actually loadable".

## Requirements

### Requirement: MCP servers registered where Claude Code loads them

`hermes install` SHALL register each manifest-declared MCP server in a configuration location that Claude Code actually reads (the `claude mcp add` store `~/.claude.json`, or a generated project `.mcp.json`). It SHALL NOT rely on `settings.json`'s `mcpServers` map, which Claude Code ignores.

#### Scenario: Manifest MCP server becomes loadable after install

- **WHEN** the manifest declares an MCP server (e.g. `macos-control`) and `hermes install` runs on a machine with the `claude` CLI present
- **THEN** the server appears in a Claude-Code-read config (`~/.claude.json` or `.mcp.json`)
- **AND** `claude mcp list` reports that server as connectable

#### Scenario: settings.json no longer carries MCP servers

- **WHEN** `hermes install` completes
- **THEN** the written `~/.claude/settings.json` contains no `mcpServers` key
- **AND** any Layer A hooks (PreToolUse / SessionStart / Stop) already present in `settings.json` are left unchanged

### Requirement: Idempotent, dry-run- and confirm-aware registration

MCP registration SHALL be idempotent and SHALL honor the existing install flags: `--dry-run` performs no mutation, and `--confirm` prompts before changing existing config.

#### Scenario: Re-running install does not duplicate servers

- **WHEN** `hermes install` runs twice with an unchanged manifest
- **THEN** the second run registers no additional copy of any MCP server and reports the server as already present

#### Scenario: Dry-run makes no changes

- **WHEN** `hermes install --dry-run` runs
- **THEN** no MCP server is registered and the planned registration actions are reported in the log

### Requirement: Migration removes stale settings.json mcpServers

When `hermes install` finds MCP servers previously written into `settings.json`'s `mcpServers` map by an earlier hermes version, it SHALL remove those stale entries so the two configs do not drift or double-register.

#### Scenario: Stale settings.json entries are cleaned up

- **WHEN** a machine's `settings.json` already contains a hermes-written `mcpServers` map and `hermes install` runs
- **THEN** those `mcpServers` entries are removed from `settings.json`
- **AND** the same servers are registered in the Claude-Code-read location instead

### Requirement: Graceful behavior when the claude CLI is absent

If MCP registration requires the `claude` CLI and it is not available, `hermes install` SHALL fail soft: surface a clear, actionable message and continue installing the rest of the manifest rather than aborting.

#### Scenario: claude CLI missing

- **WHEN** `hermes install` runs on a machine without the `claude` CLI on PATH
- **THEN** MCP registration is skipped with a surfaced warning naming the unregistered servers and the manual `claude mcp add` command to run
- **AND** the non-MCP parts of the install still complete

### Requirement: verify distinguishes "declared" from "actually loadable"

`hermes verify` SHALL report a manifest MCP server as drifted when it is declared but not registered in a Claude-Code-read location, instead of reporting `match` based solely on plugin-package presence. A server sitting only in `settings.json` SHALL NOT be counted as registered.

#### Scenario: Declared-but-unregistered MCP server is flagged

- **WHEN** a manifest MCP server is present as a plugin package but absent from `~/.claude.json` / `.mcp.json`
- **THEN** `hermes verify` reports that server as drift (e.g. `modified` / `missing`), not `match`

#### Scenario: settings.json-only registration is not accepted

- **WHEN** an MCP server exists only under `settings.json`'s `mcpServers` map
- **THEN** `hermes verify` does not treat it as registered
