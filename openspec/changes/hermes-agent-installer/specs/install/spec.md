## ADDED Requirements

### Requirement: `hermes install` reproduces the manifest on the target machine
The system SHALL provide a `hermes install` command that reads `manifest/hermes.yaml` and brings the target machine to the described state: installs the Claude Code CLI at the pinned version, restores skills, plugins, MCP server registrations, custom commands, hooks, `CLAUDE.md`, `settings.json` (minus secrets), and `keybindings.json`.

#### Scenario: Fresh machine install from a manifest
- **WHEN** `hermes install` runs on a machine with no prior `~/.claude/` directory
- **AND** `secrets.env` is present with all required env vars filled in
- **THEN** after the command exits zero, running `hermes verify` on the same machine reports no drift

### Requirement: Install is idempotent
Re-running `hermes install` on a machine that already matches the manifest MUST be a no-op with respect to file content (timestamps may change).

#### Scenario: Second install does not re-download or rewrite content
- **WHEN** `hermes install` is run twice in a row
- **THEN** the second run reports "already up to date" for every component
- **AND** no file content under `~/.claude/` changes between the two runs

### Requirement: Install fails fast on missing secrets
If the manifest references env-var placeholders that are not satisfied by the environment or `secrets.env`, `hermes install` MUST exit non-zero before writing any file, with a message listing the missing variables.

#### Scenario: Missing secret aborts install before side effects
- **WHEN** the manifest references `${OPENAI_API_KEY}` and neither the environment nor `secrets.env` defines it
- **THEN** `hermes install` exits non-zero
- **AND** the message lists `OPENAI_API_KEY` as missing
- **AND** no file under `~/.claude/` has been created or modified

### Requirement: Install preserves user-local files
`hermes install` MUST NOT touch paths excluded by the `manifest` capability (projects, sessions, history, telemetry, etc.). Existing `~/.claude/settings.local.json` MUST be left untouched if present.

#### Scenario: Local-only state is not overwritten
- **WHEN** `~/.claude/settings.local.json` exists with user-specific overrides
- **AND** `hermes install` runs
- **THEN** `settings.local.json` is unchanged after the command exits

### Requirement: Install supports dry-run
`hermes install --dry-run` SHALL print the actions it would take (install/update/skip per component) without performing them.

#### Scenario: Dry-run shows planned actions only
- **WHEN** the user runs `hermes install --dry-run`
- **THEN** stdout lists each planned action with status (would-install / would-update / unchanged)
- **AND** no file under `~/.claude/` is created or modified

### Requirement: Install lays down the Layer A `PreToolUse` hook
When `manifest/permissions.yaml` is present, `hermes install` MUST register a `PreToolUse` hook in `~/.claude/settings.json` that enforces the manifest's policy. The hook entry MUST point at a script shipped by Hermes (e.g., `~/.hermes_setup/hermes/hooks/pretooluse_enforce.py`) that reads `manifest/permissions.yaml` and rejects disallowed `Write`, `Edit`, `Bash`, `WebFetch`, and MCP tool calls. The hook MUST be installed alongside any user-authored hooks already declared in the manifest, not in place of them.

#### Scenario: Hook is installed and visible in settings
- **WHEN** `hermes install` completes against a manifest that includes `permissions.yaml`
- **THEN** `~/.claude/settings.json` contains a `hooks.PreToolUse` entry whose `command` references the Hermes enforcement script
- **AND** `hermes verify` reports the hook as `match`

### Requirement: Install ensures `bin/hermes-probe-tcc` is present and executable
`hermes install` MUST verify that `bin/hermes-probe-tcc` exists in the repo and is executable. If the file is missing, `hermes install` MUST exit non-zero with a message instructing the user to run `tools/probe-tcc/build.sh`. `hermes install` MUST NOT build the probe binary itself; that step is reserved for the maintainer and is documented in the `probe-tcc` capability.

#### Scenario: Missing probe binary aborts install
- **WHEN** `hermes install` runs in a repo where `bin/hermes-probe-tcc` is missing
- **THEN** the command exits non-zero
- **AND** the message names `tools/probe-tcc/build.sh` as the remediation
- **AND** no files under `~/.claude/` are modified

### Requirement: Install creates the runtime directory `~/.hermes/`
`hermes install` MUST ensure `~/.hermes/` exists with mode `0700` and is writable by the current user. If the directory cannot be created (read-only `~`), install MUST fall back to `~/Library/Application Support/Hermes/` and record the chosen location in `~/.claude/settings.json` so subsequent `hermes doctor` invocations find the same path.

#### Scenario: Runtime directory is created with restrictive mode
- **WHEN** `hermes install` runs on a machine where `~/.hermes/` does not yet exist
- **THEN** after install, `~/.hermes/` exists
- **AND** its mode is `0700`

### Requirement: Install generates `~/.hermes/profile.sb` when Layer B is enabled
When `manifest/permissions.yaml` contains `security.layer_b.enabled: true`, `hermes install` MUST generate a Seatbelt sandbox profile at the path declared by `security.layer_b.profile_path` (default `~/.hermes/profile.sb`). The profile is a derived artifact computed from:
1. `permissions.yaml` filesystem and shell sections — translated into `file-read*` / `file-write*` allows and process-related rules.
2. `tools/probe-tcc/sandbox-rules.yaml` — for each TCC category required by the manifest, expand to the corresponding `mach-lookup` and `appleevent-send` allows.
3. A small fixed prelude (`(version 1)`, `(deny default)`, `(import "/System/Library/Sandbox/Profiles/system.sb")`).

The generator MUST be deterministic: given the same inputs, the output MUST be byte-identical (stable rule ordering, no timestamps). The generator MUST NOT modify `~/.hermes/profile.sb` if Layer B is disabled.

Profile generation MUST happen *after* `~/.hermes/` is created and *before* `hermes install` reports success. The generated file MUST be written with mode `0600`. If the generated profile differs from the existing one byte-for-byte, install MUST log the change and overwrite atomically (temp file + `rename`).

#### Scenario: Profile is generated when Layer B is opted in
- **GIVEN** `permissions.yaml` declares `security.layer_b.enabled: true` and lists Screen Recording and Accessibility under `tcc`
- **WHEN** `hermes install` completes
- **THEN** `~/.hermes/profile.sb` exists with mode `0600`
- **AND** the file contains `(allow mach-lookup (global-name "com.apple.windowserver.active"))` and `(allow mach-lookup (global-name "com.apple.accessibility.api"))`

#### Scenario: Profile is regenerated deterministically
- **GIVEN** `~/.hermes/profile.sb` already exists from a prior install
- **WHEN** `hermes install` runs again against the same `permissions.yaml`
- **THEN** the file's content after the second install is byte-identical to its content before

#### Scenario: Install is a no-op for the profile when Layer B is disabled
- **GIVEN** an existing `~/.hermes/profile.sb` left over from a previous opt-in
- **AND** `permissions.yaml` no longer contains `security.layer_b.enabled: true`
- **WHEN** `hermes install` runs
- **THEN** install MUST NOT delete the stale profile silently
- **AND** install MUST log a warning naming the stale file
- **AND** `hermes verify` MUST flag the stale profile as drift
