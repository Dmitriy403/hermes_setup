"""Pure core for backups — restic argv, destination resolution, exclude merge.

No restic, no network. All shell-outs in the CLI go through an injected
runner so this logic is unit-testable.
"""

from __future__ import annotations

import os
from pathlib import Path
from shutil import which
from typing import Any

# Universal excludes applied to every source (additive with per-source excludes
# in backups.yaml and BACKUP_EXTRA_EXCLUDES).
DEFAULT_EXCLUDES = [
    "**/node_modules",
    "**/__pycache__",
    "**/.DS_Store",
    "**/*.pyc",
    "**/.venv",
    "**/.git/objects",
]


def restic_binary() -> str | None:
    return which("restic")


def _expand(p: str) -> str:
    return os.path.expanduser(p)


# ---- destination → restic repository string ----


def destination_repo(destination: dict[str, Any]) -> str:
    """Resolve a backups.yaml `destination` block to a restic -r value.

    kind: local | external_disk → the literal `path`.
    kind: rclone:<remote>       → rclone:<remote>:<repo> (repo default 'hermes-backups').
    """
    kind = (destination or {}).get("kind", "local")
    if kind.startswith("rclone:"):
        remote = kind.split(":", 1)[1]
        repo = destination.get("repo", "hermes-backups")
        return f"rclone:{remote}:{repo}"
    # local / external_disk
    path = destination.get("path")
    if not path:
        raise ValueError(f"destination kind '{kind}' requires a 'path'")
    return _expand(path)


# ---- exclude merging ----


def merge_excludes(manifest_excludes: list[str] | None, extra_env: str | None) -> list[str]:
    out: list[str] = list(DEFAULT_EXCLUDES)
    for e in manifest_excludes or []:
        if e not in out:
            out.append(e)
    for e in (extra_env or "").split(":"):
        e = e.strip()
        if e and e not in out:
            out.append(e)
    return out


# ---- restic argv builders ----


def backup_argv(repo: str, sources: list[str], excludes: list[str], *, dry_run: bool = False) -> list[str]:
    argv = ["restic", "-r", repo, "backup", *[_expand(s) for s in sources]]
    for e in excludes:
        argv += ["--exclude", e]
    if dry_run:
        argv.append("--dry-run")
    return argv


def check_argv(repo: str) -> list[str]:
    return ["restic", "-r", repo, "check"]


def restore_argv(repo: str, target: str, path: str | None = None, snapshot: str | None = None) -> list[str]:
    argv = ["restic", "-r", repo, "restore", snapshot or "latest", "--target", _expand(target)]
    if path:
        argv += ["--include", _expand(path)]
    return argv


# ---- backups.yaml ----


def load_config(path: str | Path) -> dict[str, Any]:
    import yaml
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"backups config not found: {p}")
    return yaml.safe_load(p.read_text()) or {}


def collect_sources_and_excludes(config: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Flatten backups.yaml sources into (paths, merged-excludes)."""
    sources: list[str] = []
    per_source_excludes: list[str] = []
    for entry in config.get("sources", []) or []:
        if isinstance(entry, str):
            sources.append(entry)
        elif isinstance(entry, dict) and entry.get("path"):
            sources.append(entry["path"])
            per_source_excludes.extend(entry.get("excludes", []) or [])
    excludes = merge_excludes(
        (config.get("excludes", []) or []) + per_source_excludes,
        os.environ.get("BACKUP_EXTRA_EXCLUDES"),
    )
    return sources, excludes
