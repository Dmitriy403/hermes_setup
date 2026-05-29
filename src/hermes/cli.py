"""Top-level `hermes` CLI dispatcher.

Only the `doctor` subcommand is wired up so far. capture/install/verify land
with their respective task sections.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("usage: hermes <command> [options]\n\ncommands:\n"
              "  capture  snapshot ~/.claude into the manifest\n"
              "  install  replay the manifest onto this machine\n"
              "  verify   diff this machine against the manifest\n"
              "  doctor   macOS TCC and capability checkup\n"
              "  run      launch claude, optionally under the Layer B sandbox")
        return 64

    command, rest = argv[0], argv[1:]
    if command == "doctor":
        from .doctor.cli import main as doctor_main

        return doctor_main(rest)
    if command == "run":
        from .run import main as run_main

        return run_main(rest)
    if command == "capture":
        return _capture_cmd(rest)
    if command == "install":
        return _install_cmd(rest)
    if command == "verify":
        return _verify_cmd(rest)
    if command == "capabilities":
        return _capabilities_cmd(rest)

    print(f"unknown command: {command}", file=sys.stderr)
    print("commands: capture, install, verify, capabilities, doctor, run", file=sys.stderr)
    return 64


def _arg_value(argv: list[str], flag: str) -> str | None:
    """Pull `--flag value` or `--flag=value` out of a raw argv list."""
    for i, a in enumerate(argv):
        if a == flag and i + 1 < len(argv):
            return argv[i + 1]
        if a.startswith(flag + "="):
            return a.split("=", 1)[1]
    return None


def _capabilities_cmd(argv: list[str]) -> int:
    import json as _json

    from . import paths
    from .permissions import Permissions, render_capabilities

    manifest_dir = _arg_value(argv, "--manifest-dir")
    perms = Permissions.load(paths.permissions_yaml_path(manifest_dir))
    if "--json" in argv:
        print(_json.dumps({
            "filesystem": {"write_exec": perms.fs_write_exec, "write": perms.fs_write,
                           "read": perms.fs_read, "forbidden": perms.fs_forbidden},
            "shell": {"allow": perms.shell_allow, "ask": perms.shell_ask, "deny": perms.shell_deny},
            "network": {"domains": perms.network_domains, "default": perms.network_default},
            "mcp": {"enabled": perms.mcp_enabled, "disabled": perms.mcp_disabled},
        }, indent=2, sort_keys=True))
    else:
        print(render_capabilities(perms))
    return 0


def _verify_cmd(argv: list[str]) -> int:
    import argparse

    from .manifest import ManifestError
    from .verify import has_drift, render_human, render_json, verify

    p = argparse.ArgumentParser(prog="hermes verify",
                                description="Diff this machine against the manifest.")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--manifest-dir", help="config repo root (default: HERMES_MANIFEST_DIR or the tool's manifest/)")
    try:
        args = p.parse_args(argv)
    except SystemExit:
        return 64

    try:
        records = verify(config_root=args.manifest_dir)
    except ManifestError as exc:
        print(f"verify: {exc}", file=sys.stderr)
        return 1
    print(render_json(records) if args.json else render_human(records))
    return 1 if has_drift(records) else 0


def _install_cmd(argv: list[str]) -> int:
    import argparse

    from .install.installer import InstallError, install
    from .manifest import ManifestError

    p = argparse.ArgumentParser(prog="hermes install",
                                description="Replay the manifest onto this machine.")
    p.add_argument("--dry-run", action="store_true", help="print actions without writing")
    p.add_argument("--manifest-dir", help="config repo root (default: HERMES_MANIFEST_DIR or the tool's manifest/)")
    try:
        args = p.parse_args(argv)
    except SystemExit:
        return 64

    try:
        result = install(config_root=args.manifest_dir, dry_run=args.dry_run)
    except (InstallError, ManifestError) as exc:
        print(f"install aborted: {exc}", file=sys.stderr)
        return 1

    label = "[dry-run] " if args.dry_run else ""
    for action in result.actions:
        print(f"  {label}{action}")
    print(f"\n{label}install complete.")
    return 0


def _capture_cmd(argv: list[str]) -> int:
    import argparse

    from .capture import COMPONENTS, capture

    p = argparse.ArgumentParser(prog="hermes capture",
                                description="Snapshot ~/.claude into the manifest.")
    p.add_argument("--only", help="comma-separated components to capture")
    p.add_argument("--skip", help="comma-separated components to skip")
    p.add_argument("--dry-run", action="store_true", help="print actions without writing")
    p.add_argument("--manifest-dir", help="config repo root to write into (default: HERMES_MANIFEST_DIR or the tool's manifest/)")
    try:
        args = p.parse_args(argv)
    except SystemExit:
        return 64

    only = args.only.split(",") if args.only else None
    skip = args.skip.split(",") if args.skip else None
    for sel in (only or []) + (skip or []):
        if sel not in COMPONENTS:
            print(f"unknown component: {sel}", file=sys.stderr)
            print(f"valid: {', '.join(COMPONENTS)}", file=sys.stderr)
            return 64

    result = capture(config_root=args.manifest_dir, only=only, skip=skip, dry_run=args.dry_run)
    label = "[dry-run] " if args.dry_run else ""
    for action in result.actions:
        print(f"  {label}{action}")
    m = result.manifest
    print(f"\n{label}captured: {len(m.skills)} skills, {len(m.plugins)} plugins, "
          f"{len(m.mcp_servers)} mcp servers, {len(m.commands)} commands, {len(m.hooks)} hooks")
    if result.redactor.discovered:
        print(f"{label}redacted {len(result.redactor.discovered)} secret(s): "
              f"{', '.join(sorted(result.redactor.discovered))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
