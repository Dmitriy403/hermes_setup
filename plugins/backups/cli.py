"""`hermes-backup` — thin restic wrapper driven by manifest/backups.yaml.

Subcommands: backup [--dry-run], verify, restore. Fails soft when restic is
absent (Decision 18). On a failed backup, routes a failure notification.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from . import core, notify


def _config_path(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    base = os.environ.get("HERMES_MANIFEST_DIR")
    if base:
        return Path(base) / "manifest" / "backups.yaml"
    return Path("manifest/backups.yaml")


def _require_restic() -> str | None:
    return core.restic_binary()


def _run(argv: list[str]) -> int:
    proc = subprocess.run(argv)
    return proc.returncode


def cmd_backup(config_path: Path, *, dry_run: bool) -> int:
    if not _require_restic():
        print("hermes-backup: restic not found — `brew install restic`", file=sys.stderr)
        return 10
    cfg = core.load_config(config_path)
    repo = core.destination_repo(cfg.get("destination", {}))
    sources, excludes = core.collect_sources_and_excludes(cfg)
    if not sources:
        print("hermes-backup: no sources in backups.yaml", file=sys.stderr)
        return 64
    argv = core.backup_argv(repo, sources, excludes, dry_run=dry_run)
    rc = _run(argv)
    if rc != 0 and not dry_run:
        notifiers = notify.build_notifiers(dict(os.environ))
        notify.notify_failure("Hermes backup FAILED",
                              f"restic exited {rc} for repo {repo}", notifiers)
    return rc


def cmd_verify(config_path: Path) -> int:
    if not _require_restic():
        print("hermes-backup: restic not found — `brew install restic`", file=sys.stderr)
        return 10
    cfg = core.load_config(config_path)
    repo = core.destination_repo(cfg.get("destination", {}))
    return _run(core.check_argv(repo))


def cmd_restore(config_path: Path, target: str, path: str | None, snapshot: str | None) -> int:
    if not _require_restic():
        print("hermes-backup: restic not found — `brew install restic`", file=sys.stderr)
        return 10
    cfg = core.load_config(config_path)
    repo = core.destination_repo(cfg.get("destination", {}))
    return _run(core.restore_argv(repo, target, path, snapshot))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hermes-backup", description="restic backups driven by backups.yaml.")
    p.add_argument("--config", help="path to backups.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backup"); b.add_argument("--dry-run", action="store_true")
    sub.add_parser("verify")
    r = sub.add_parser("restore")
    r.add_argument("--target", required=True)
    r.add_argument("--path")
    r.add_argument("--snapshot", default="latest")
    try:
        args = p.parse_args(argv)
    except SystemExit:
        return 64

    cfg_path = _config_path(args.config)
    try:
        if args.cmd == "backup":
            return cmd_backup(cfg_path, dry_run=args.dry_run)
        if args.cmd == "verify":
            return cmd_verify(cfg_path)
        if args.cmd == "restore":
            return cmd_restore(cfg_path, args.target, args.path, args.snapshot)
    except FileNotFoundError as exc:
        print(f"hermes-backup: {exc}", file=sys.stderr)
        return 64
    return 64


if __name__ == "__main__":
    raise SystemExit(main())
