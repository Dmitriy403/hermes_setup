## ADDED Requirements

### Requirement: `hermes capture` snapshots the current machine
The system SHALL provide a `hermes capture` command that scans the running user's Claude Code installation and writes a manifest under `manifest/` describing the components enumerated in the `manifest` capability.

#### Scenario: Capture writes a manifest from a configured machine
- **WHEN** the user runs `hermes capture` on a machine with `~/.claude/` populated
- **THEN** `manifest/hermes.yaml` is created or updated and every required component is described
- **AND** the command exits zero
- **AND** running `hermes capture` a second time with no environmental changes produces no diff (idempotency)

### Requirement: Capture is non-destructive to the source machine
`hermes capture` MUST NOT modify `~/.claude/` or any other system file on the source machine; it only reads and writes inside the repo working tree.

#### Scenario: Source machine remains untouched
- **WHEN** `hermes capture` runs
- **THEN** the mtime and content of every file under `~/.claude/` is unchanged

### Requirement: Capture redacts secrets
`hermes capture` MUST replace secret-shaped values (API keys, tokens, anything matched by configurable redaction patterns) with `${ENV_VAR_NAME}` references and record those names in `secrets.env.example`. Default redaction patterns SHALL include common API-key shapes (e.g., `sk-…`, `ghp_…`, long hex/base64 strings in fields named like `*_KEY`, `*_TOKEN`, `*_SECRET`).

#### Scenario: API key in MCP env map is redacted
- **WHEN** `~/.claude/settings.json` contains an MCP server with `env.ANTHROPIC_API_KEY` set to a literal `sk-…` value
- **THEN** the captured manifest stores `env.ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY}"`
- **AND** `secrets.env.example` lists `ANTHROPIC_API_KEY=` with a placeholder

### Requirement: Capture supports selective scopes
`hermes capture` SHALL accept flags to capture a subset of components, e.g., `--only skills,plugins` or `--skip mcp`. Without flags it captures everything.

#### Scenario: Selective capture only updates requested components
- **WHEN** the user runs `hermes capture --only skills`
- **THEN** only the skills section of the manifest is updated
- **AND** other manifest sections remain byte-identical to before the command
