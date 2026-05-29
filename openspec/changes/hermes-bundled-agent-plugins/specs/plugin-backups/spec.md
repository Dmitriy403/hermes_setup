## ADDED Requirements

### Requirement: Backup plugin manages restic-based snapshots on a schedule
The repo SHALL contain `plugins/backups/` providing: (a) a declarative `manifest/backups.yaml` listing source paths and destination repositories, (b) a thin wrapper CLI `hermes-backup` that runs `restic backup` per the manifest, and (c) a `launchd` plist generator that schedules periodic runs.

#### Scenario: `hermes install` schedules the backup job
- **WHEN** `hermes install` runs on macOS with a populated `manifest/backups.yaml`
- **THEN** a launchd plist is installed at `~/Library/LaunchAgents/com.hermes.backup.plist`
- **AND** `launchctl list | grep com.hermes.backup` reports it as loaded

### Requirement: Default-protected paths
The default `manifest/backups.yaml` SHALL include these source paths (each user-removable):
- `~/.hermes_setup/` (the manifest repo itself)
- `~/.claude/` minus all ephemeral paths excluded by the `manifest` capability
- `~/Documents/`
- The user's secret vault path if declared via `BACKUP_SECRETS_PATH`

#### Scenario: Default backup covers the manifest repo
- **WHEN** the user runs `hermes-backup --dry-run` immediately after `hermes install`
- **THEN** the planned-files list includes every file under `~/.hermes_setup/` that is not gitignored

### Requirement: Excluded paths are honored
The backup MUST exclude the same ephemeral paths the manifest excludes (sessions, telemetry, caches, debug logs, `node_modules/`, `__pycache__/`, `.git/objects` if the repo can be re-cloned, etc.). Exclusions SHALL be expressed in `manifest/backups.yaml` and additive via `BACKUP_EXTRA_EXCLUDES`.

#### Scenario: Ephemeral data is never in the snapshot
- **WHEN** a backup run completes
- **AND** the user inspects the snapshot with `restic ls latest`
- **THEN** no file path under any excluded directory appears in the snapshot

### Requirement: Destination is user-chosen and credential-driven
`manifest/backups.yaml` SHALL declare a `destination` block with a `kind` of `local`, `external_disk`, or `rclone:<remote>` (for any cloud supported by rclone — S3, B2, Google Drive, etc.). Destination credentials MUST live in `secrets.env`, referenced as `${VAR}` from the manifest.

#### Scenario: Cloud destination via rclone
- **WHEN** `destination.kind` is `rclone:b2_personal` and `secrets.env` provides `RCLONE_B2_KEY_ID` and `RCLONE_B2_APP_KEY`
- **THEN** `hermes-backup` runs `restic` with the `rclone:b2_personal:hermes-backups` repository
- **AND** the secrets never appear in any committed file

### Requirement: Backups are verifiable and restorable
The plugin SHALL provide:
- `hermes-backup verify`: runs `restic check` and reports integrity.
- `hermes-backup restore --target=<dir> [--path=<source-glob>] [--snapshot=<id|latest>]`: restores files into a target directory (default: a temp path so the user explicitly opts in to overwriting).

#### Scenario: Verify on healthy repo exits clean
- **WHEN** `hermes-backup verify` runs against a healthy repo
- **THEN** the exit code is 0 and the output ends with "no errors were found"

#### Scenario: Restore writes to a target dir without overwriting source
- **WHEN** `hermes-backup restore --target=/tmp/restore-test --path=~/Documents`
- **THEN** files appear under `/tmp/restore-test/Documents/` and the original `~/Documents/` is unchanged

### Requirement: Backup failures surface to the operator
On every scheduled run that fails (non-zero exit, repo lock conflict, missing destination), the plugin MUST send a notification:
1. A macOS notification via the `macos-control` plugin's `notify` tool (or `osascript display notification` as fallback if MCP unreachable), AND
2. If `telegram-bot` is registered and `BACKUP_ALERT_CHAT_ID` is set, a Telegram message to that chat with the failure summary.

#### Scenario: Failed scheduled run alerts via Telegram
- **WHEN** a scheduled backup fails because the destination disk is not mounted
- **AND** `BACKUP_ALERT_CHAT_ID` is set
- **THEN** within 60 seconds a Telegram message arrives at that chat with subject "Hermes backup FAILED" and the restic stderr tail
