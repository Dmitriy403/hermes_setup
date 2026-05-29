## ADDED Requirements

### Requirement: `install.sh` bootstraps a fresh machine
The repo SHALL include an `install.sh` script at its root that, when executed on a machine with only `curl` and a POSIX shell, installs all prerequisites (git, the chosen CLI runtime, and the `claude` CLI), clones or updates this repo into a stable location (default `~/.hermes_setup`), and runs `hermes install`.

#### Scenario: One-shot bootstrap from curl
- **WHEN** a user on a fresh machine runs `curl -fsSL <repo-url>/install.sh | sh`
- **AND** is prompted to provide secrets when asked
- **THEN** the script exits zero
- **AND** `~/.claude/` is populated according to the manifest
- **AND** running `hermes verify` reports no drift

### Requirement: Bootstrap is non-interactive when configured
`install.sh` SHALL accept `HERMES_SECRETS_FILE=/path/to/secrets.env` and `HERMES_NONINTERACTIVE=1` so it can run in CI or other unattended contexts without prompting.

#### Scenario: Non-interactive bootstrap succeeds in CI
- **WHEN** `install.sh` is invoked with `HERMES_NONINTERACTIVE=1 HERMES_SECRETS_FILE=/tmp/secrets.env`
- **AND** `/tmp/secrets.env` contains all required variables
- **THEN** the script never reads from stdin
- **AND** it exits zero

### Requirement: Bootstrap is safe to re-run
Running `install.sh` again on an already-installed machine MUST behave identically to running `hermes install`: idempotent, no destructive operations on existing config beyond what the manifest dictates.

#### Scenario: Re-running bootstrap is a no-op
- **WHEN** `install.sh` is run twice in succession on the same machine
- **THEN** the second run reports "already up to date" for every component
- **AND** no file under `~/.claude/` differs between the two runs (content-wise)
