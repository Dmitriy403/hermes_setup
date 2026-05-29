"""launchd plist for the scheduled backup job (periodic StartInterval)."""

from __future__ import annotations

import plistlib

BACKUP_LABEL = "com.hermes.backup"


def generate_periodic_plist(
    label: str,
    program_arguments: list[str],
    interval_seconds: int,
    *,
    stdout_path: str | None = None,
    stderr_path: str | None = None,
) -> str:
    d: dict = {
        "Label": label,
        "ProgramArguments": list(program_arguments),
        "StartInterval": int(interval_seconds),
        "RunAtLoad": False,
        "ProcessType": "Background",
    }
    if stdout_path:
        d["StandardOutPath"] = stdout_path
    if stderr_path:
        d["StandardErrorPath"] = stderr_path
    return plistlib.dumps(d, fmt=plistlib.FMT_XML).decode("utf-8")


def backup_plist(hermes_backup_bin: str, interval_seconds: int = 3600,
                 *, stderr_path: str | None = None) -> str:
    """LaunchAgent that runs `hermes-backup backup` every interval_seconds."""
    return generate_periodic_plist(
        BACKUP_LABEL, [hermes_backup_bin, "backup"], interval_seconds, stderr_path=stderr_path)
