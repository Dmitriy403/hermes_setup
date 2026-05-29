# backups

`restic`-based scheduled snapshots of a user-declared path set, to a local
disk, external drive, or any `rclone` cloud remote. Driven by
`manifest/backups.yaml`; scheduled via launchd.

## CLI

```sh
hermes-backup backup [--dry-run]     # snapshot per backups.yaml
hermes-backup verify                 # restic check (integrity)
hermes-backup restore --target=<dir> [--path=<glob>] [--snapshot=<id|latest>]
```

`restore` writes into `--target` (you opt in to overwriting) and never touches
the source.

## backups.yaml

- `sources`: paths (with optional per-path `excludes`). Defaults cover
  `~/.hermes_setup`, `~/.claude` (minus ephemerals), `~/Documents`.
- `excludes`: extra patterns (universal ones — `node_modules`, `__pycache__`,
  `.DS_Store`, `.git/objects`, … — are added automatically; `BACKUP_EXTRA_EXCLUDES`
  is colon-separated and additive).
- `destination.kind`: `local` | `external_disk` | `rclone:<remote>`.
  Credentials live in `secrets.env` as `${VAR}` (never in the manifest).
- `schedule.interval_seconds`: launchd cadence (default hourly).

## Failure alerts

A failed scheduled run sends a macOS notification, and — if `BACKUP_ALERT_CHAT_ID`
+ `TELEGRAM_BOT_TOKEN` are set — a Telegram message ("Hermes backup FAILED" +
the restic error tail).

## Dependencies (lazy / brew)

- `restic` — `brew install restic`. `rclone` — `brew install rclone` (cloud only).
  If absent, the CLI exits with a `brew install` hint.

## Smoke test (needs restic)

```sh
hermes-backup backup --dry-run    # lists planned files (no write)
hermes-backup verify              # "no errors were found"
```
