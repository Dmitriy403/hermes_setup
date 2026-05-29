"""launchd plist generation (pure, testable).

Produces a LaunchAgent plist so the long-poll worker runs at login and
restarts on crash. The same helper is reused by the backups plugin.
"""

from __future__ import annotations

import plistlib
from typing import Any


def generate_plist(
    label: str,
    program_arguments: list[str],
    *,
    run_at_load: bool = True,
    keep_alive: bool = True,
    env: dict[str, str] | None = None,
    stdout_path: str | None = None,
    stderr_path: str | None = None,
) -> str:
    """Return a launchd LaunchAgent plist as XML text."""
    d: dict[str, Any] = {
        "Label": label,
        "ProgramArguments": list(program_arguments),
        "RunAtLoad": run_at_load,
        "KeepAlive": keep_alive,
        "ProcessType": "Background",
    }
    if env:
        d["EnvironmentVariables"] = dict(env)
    if stdout_path:
        d["StandardOutPath"] = stdout_path
    if stderr_path:
        d["StandardErrorPath"] = stderr_path
    return plistlib.dumps(d, fmt=plistlib.FMT_XML).decode("utf-8")


TELEGRAM_LABEL = "com.hermes.telegram-bot"


def telegram_plist(python: str, *, stdout_path: str | None = None,
                   stderr_path: str | None = None) -> str:
    """LaunchAgent for the telegram-bot long-poll worker."""
    return generate_plist(
        TELEGRAM_LABEL,
        [python, "-m", "telegram_bot.worker"],
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )
