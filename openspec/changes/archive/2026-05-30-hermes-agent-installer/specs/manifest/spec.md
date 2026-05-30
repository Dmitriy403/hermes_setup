## ADDED Requirements

### Requirement: Manifest file location and format
The system SHALL store the environment description in a top-level file `manifest/hermes.yaml` (the "root manifest") plus per-component subdirectories under `manifest/` (e.g., `manifest/skills/`, `manifest/plugins/`, `manifest/mcp/`, `manifest/settings/`, `manifest/hooks/`, `manifest/commands/`). The root manifest MUST be valid YAML and MUST declare a `schema_version` field.

#### Scenario: Root manifest is valid YAML with schema version
- **WHEN** any `hermes` subcommand reads `manifest/hermes.yaml`
- **THEN** parsing succeeds and `schema_version` is present at the top level
- **AND** if `schema_version` is missing or unsupported the command exits non-zero with an explanatory error

### Requirement: Manifest describes every reproducible component
The manifest SHALL describe each of the following components such that, given only the manifest plus `secrets.env`, the target machine can be brought to the same Claude Code state:
1. Claude Code CLI version (or a "latest" pin).
2. Skills installed under `~/.claude/skills/` (name + source: local copy, git URL, or marketplace).
3. Plugins installed under `~/.claude/plugins/` (name + marketplace + version).
4. MCP servers registered in `~/.claude/settings.json` (name, command, args, env-var references — never literal secrets).
5. The contents of `~/.claude/CLAUDE.md`.
6. The contents of `~/.claude/settings.json` minus any fields that contain secrets.
7. Custom commands under `~/.claude/commands/`.
8. Hooks (referenced from `settings.json`).
9. Keybindings file `~/.claude/keybindings.json` if present.

#### Scenario: Each component has a manifest entry
- **WHEN** the user inspects `manifest/hermes.yaml` after `hermes capture`
- **THEN** every component listed above is represented either inline or via a referenced file under `manifest/`
- **AND** every referenced file exists in the repo

### Requirement: Manifest excludes secrets and ephemeral data
The manifest MUST NOT contain literal API keys, OAuth tokens, session cookies, conversation history, telemetry, debug logs, caches, or any path under `~/.claude/{projects,sessions,history.jsonl,todos,telemetry,debug,cache,paste-cache,backups,file-history,shell-snapshots,mcp-needs-auth-cache.json,vscode-claude-status-cache.json,settings.local.json,ide,session-env}`.

#### Scenario: Secrets are referenced by env var, not value
- **WHEN** an MCP server in the live `settings.json` has an `env` map with values that look like secrets (e.g., API keys)
- **THEN** the corresponding manifest entry stores `env: { KEY: "${ENV_VAR_NAME}" }` and adds `ENV_VAR_NAME` to a `secrets.env.example` template
- **AND** the literal secret value never appears in any file under `manifest/`

#### Scenario: Ephemeral paths are excluded
- **WHEN** `hermes capture` runs
- **THEN** no file under any excluded path is read into or referenced from the manifest

### Requirement: Manifest declares the security surface as `permissions.yaml`
The manifest SHALL include a top-level `manifest/permissions.yaml` file that declaratively describes the capabilities the Hermes/Claude environment is allowed to use. The file is the single source of truth consumed by the Layer A `PreToolUse` hook, the Layer B Seatbelt profile (when opted in), the `doctor` capability, and `hermes capabilities`. The file MUST define the following top-level sections:
1. `filesystem` with sub-lists `write-exec`, `write`, `read`, `forbidden` — each a list of glob patterns. Paths in `forbidden` MUST cause Layer A to block matching `Write`, `Edit`, and `Bash` access even if a broader allow pattern would otherwise match.
2. `shell` with sub-lists `allow`, `ask`, `deny` — each a list of command-name or command-prefix patterns.
3. `network` with sub-fields `domains` (list of allowed domains for `WebFetch` and outbound HTTPS) and `default` (`allow` or `deny`).
4. `mcp` with `enabled` and `disabled` lists.
5. `tcc` with sub-keys per category. `automation.targets[]` MUST be a list of `{bundle-id, required-by[], reason}` entries. `files[]` MUST be a list of `{path, required-by[]}` entries. Each section MUST declare which plugin(s) require it via `required-by[]`.

Plugins MUST NOT re-declare these capabilities in plugin-specific spec files; the aggregator is `permissions.yaml`.

#### Scenario: Manifest contains a permissions file
- **WHEN** the user inspects the manifest directory after `hermes capture`
- **THEN** `manifest/permissions.yaml` exists
- **AND** it contains at minimum the `filesystem`, `shell`, `network`, `mcp`, and `tcc` top-level sections

#### Scenario: TCC requirements name their consumers
- **WHEN** `manifest/permissions.yaml` declares `tcc.screen-recording.required-by: [macos-control]`
- **AND** `manifest/mcp/macos-control.yaml` is NOT present in the manifest
- **THEN** `hermes verify` reports a manifest consistency error: "tcc.screen-recording requires macos-control which is not in the manifest"

### Requirement: Network filtering granularity is documented
The manifest specification MUST document that `network.domains` is enforced only by the Layer A `PreToolUse` hook for tool calls Hermes can intercept (`WebFetch`, MCP tools that take a URL). When Layer B (Seatbelt) is opted in, the generated sandbox profile applies only port-level network rules; domain-level filtering remains the responsibility of Layer A. Users MUST NOT assume that Layer B alone enforces `network.domains`.

#### Scenario: Domain enforcement is Layer A's responsibility
- **WHEN** the user opts into Layer B (`hermes run`) and `network.domains` is set to `[gitcode.com]`
- **AND** Claude attempts an MCP tool call that opens a TCP socket to `evil.example.com:443`
- **THEN** the Seatbelt profile does NOT block the connection by domain (Seatbelt cannot filter by domain)
- **AND** the Layer A `PreToolUse` hook IS responsible for blocking the call before it reaches the OS
- **AND** the manifest documentation explicitly states this limitation

### Requirement: `permissions.yaml` declares optional Layer B settings
The schema for `manifest/permissions.yaml` SHALL include an optional top-level `security` section with sub-key `layer_b`. When present, `security.layer_b` MUST contain:
- `enabled: bool` (default `false`) — whether `hermes install` should generate a Seatbelt profile.
- `profile_path: string` (default `~/.hermes/profile.sb`) — where the generated profile lives. The path MUST be inside the user's home directory; absolute paths outside `~` are rejected on install.

When `security.layer_b.enabled` is `false` or the entire `security` section is absent, `hermes install` MUST NOT generate a Seatbelt profile, and `hermes doctor` MUST NOT run a sandboxed pass.

#### Scenario: Absent security section disables Layer B
- **GIVEN** `manifest/permissions.yaml` has no `security` top-level section
- **WHEN** `hermes install` runs
- **THEN** no file at `~/.hermes/profile.sb` is created or modified
- **AND** `hermes doctor` runs only the baseline probe pass

#### Scenario: Enabled Layer B triggers profile generation
- **GIVEN** `manifest/permissions.yaml` contains `security.layer_b.enabled: true`
- **WHEN** `hermes install` runs
- **THEN** `~/.hermes/profile.sb` exists and is non-empty after install
- **AND** the profile's content is derived deterministically from the rest of `permissions.yaml` plus `tools/probe-tcc/sandbox-rules.yaml`
