"""Install-time launchd LaunchAgent plist generation (tool-side).

Builds the plist for a registered plugin's job — KeepAlive worker (telegram)
or periodic StartInterval (backups). Kept in the tool so install does not need
to import the plugin packages to schedule them.
"""

from __future__ import annotations

import plistlib
from pathlib import Path


def launch_agents_dir(home: Path) -> Path:
    return home / "Library" / "LaunchAgents"


def generate_agent_plist(
    label: str,
    program_arguments: list[str],
    *,
    keep_alive: bool = False,
    start_interval: int | None = None,
    env: dict[str, str] | None = None,
    stdout_path: str | None = None,
    stderr_path: str | None = None,
) -> str:
    d: dict = {
        "Label": label,
        "ProgramArguments": list(program_arguments),
        "ProcessType": "Background",
    }
    if keep_alive:
        d["KeepAlive"] = True
        d["RunAtLoad"] = True
    if start_interval is not None:
        d["StartInterval"] = int(start_interval)
        d["RunAtLoad"] = False
    if env:
        # launchd jobs don't inherit the login shell env, so secrets the job
        # needs (e.g. RESTIC_PASSWORD) must be embedded here.
        d["EnvironmentVariables"] = dict(env)
    if stdout_path:
        d["StandardOutPath"] = stdout_path
    if stderr_path:
        d["StandardErrorPath"] = stderr_path
    return plistlib.dumps(d, fmt=plistlib.FMT_XML).decode("utf-8")
