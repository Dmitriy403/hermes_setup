"""Plugin external-dependency check (design.md Decision 18).

Report-only: runs ``shutil.which`` for each bundled plugin's external binary
and lists the missing ones with their ``brew install`` command. Doctor never
installs anything (symmetric with its TCC stance).
"""

from __future__ import annotations

from dataclasses import dataclass
from shutil import which

# plugin -> external binaries it needs. macos-control (osascript/screencapture)
# is omitted: those ship with macOS. vision uses the `anthropic` SDK (a pip
# dependency for headless mode), not a system binary.
PLUGIN_DEPENDENCIES: dict[str, list[dict]] = {
    "voice": [
        {"name": "whisper.cpp", "binaries": ["whisper-cli", "whisper-cpp"], "brew": "whisper-cpp"},
        {"name": "ffmpeg", "binaries": ["ffmpeg"], "brew": "ffmpeg"},
    ],
    "backups": [
        {"name": "restic", "binaries": ["restic"], "brew": "restic"},
        {"name": "rclone", "binaries": ["rclone"], "brew": "rclone"},
    ],
}


@dataclass
class DepStatus:
    plugin: str
    name: str
    present: bool
    found_at: str | None
    brew: str


def check_plugin_deps() -> list[DepStatus]:
    out: list[DepStatus] = []
    for plugin, deps in PLUGIN_DEPENDENCIES.items():
        for dep in deps:
            found = next((p for p in (which(b) for b in dep["binaries"]) if p), None)
            out.append(DepStatus(
                plugin=plugin, name=dep["name"],
                present=found is not None, found_at=found, brew=dep["brew"],
            ))
    return out


def render(deps: list[DepStatus]) -> str:
    lines = ["Plugin dependencies", ""]
    missing = [d for d in deps if not d.present]
    for d in deps:
        mark = f"ok ({d.found_at})" if d.present else "MISSING"
        lines.append(f"  [{mark:>24}] {d.plugin}: {d.name}")
    lines.append("")
    if missing:
        lines.append("To enable the plugins that need them:")
        for pkg in sorted({d.brew for d in missing}):
            lines.append(f"  brew install {pkg}")
    else:
        lines.append("All plugin dependencies present.")
    return "\n".join(lines)
