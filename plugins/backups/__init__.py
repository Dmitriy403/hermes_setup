"""backups — restic-based scheduled snapshots for the Hermes agent.

Pure core (destination resolution, restic argv, exclude merging) +
injected runner for the live restic calls + a failure-notification router.
The `hermes-backup` CLI and a launchd plist generator compose these.
"""
