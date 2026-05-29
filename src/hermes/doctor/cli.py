"""`hermes doctor` command — orchestrates probe passes, classification,
rendering, and the action modes (--fix / --reset / --mdm-profile /
--suggest-sandbox-patch)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from .. import paths
from . import fix as fixmod
from . import mdm, probe, report, settings_urls
from .cache import Cache
from .classify import (
    baseline_exit_code,
    classify_baseline,
    classify_differential,
    differential_exit_code,
)

USAGE_ERROR = 64
PROBE_ERROR = 10


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hermes doctor", description="macOS TCC and capability checkup.")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="read-only checkup (default)")
    mode.add_argument("--fix", action="store_true", help="open System Settings for each missing category")
    mode.add_argument("--warmup", action="store_true", help="trigger TCC prompts for not-determined categories")
    mode.add_argument("--reset", metavar="CATEGORY", help="tccutil reset the named category")
    mode.add_argument("--mdm-profile", action="store_true", help="emit a PPPC .mobileconfig payload")
    mode.add_argument("--suggest-sandbox-patch", action="store_true", help="print a diff that closes Layer B gaps")
    mode.add_argument("--plugin-deps", action="store_true", help="report missing plugin external binaries")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--strict", action="store_true", help="treat misalignment/extra grants as errors")
    p.add_argument("--exit-zero", action="store_true", help="always exit 0 (report-only signal)")
    p.add_argument("--with-sandbox", metavar="PATH", help="force a Layer B sandboxed pass against PATH")
    p.add_argument("--yes", action="store_true", help="skip confirmation prompts (for --reset)")
    return p


def _run_reset(category: str, assume_yes: bool) -> int:
    name = settings_urls.tccutil_name(category)
    if not name:
        print(f"unknown reset category: {category}", file=sys.stderr)
        print(f"known: {', '.join(settings_urls.known_categories())}", file=sys.stderr)
        return USAGE_ERROR
    if not assume_yes:
        try:
            ans = input(f"tccutil reset {name}? This revokes the permission. [y/N] ")
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            return 0
        if ans.strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return 0
    proc = subprocess.run(["tccutil", "reset", name], capture_output=True, text=True)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return USAGE_ERROR

    # --reset is a standalone action.
    if args.reset:
        return _run_reset(args.reset, args.yes)

    # --plugin-deps is a standalone, probe-free report (Decision 18).
    if args.plugin_deps:
        from . import plugin_deps as pd
        deps = pd.check_plugin_deps()
        if args.json:
            import json as _json
            print(_json.dumps({"plugin_dependencies": [vars(d) for d in deps]},
                              indent=2, sort_keys=True))
        else:
            print(pd.render(deps))
        return 0

    warnings: list[str] = []
    if paths.using_fallback_home():
        warnings.append("~/.hermes not writable; using ~/Library/Application Support/Hermes")

    cache, cache_warn = Cache.load(paths.probe_cache_path())
    if cache_warn:
        warnings.append(cache_warn)

    # Resolve probe binary.
    try:
        binary = probe.resolve_binary(cache.probe_binary_path())
    except probe.ProbeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return PROBE_ERROR

    exp = probe.expectations(with_sandbox=args.with_sandbox)

    # Decide whether to run a differential (Layer B) pass.
    layer_b_requested = exp.layer_b.enabled and bool(exp.layer_b.profile_path)
    profile_exists = layer_b_requested and Path(exp.layer_b.profile_path).exists()
    nested = probe.doctor_is_sandboxed()
    differential = bool(profile_exists) and not nested
    if layer_b_requested and nested:
        warnings.append(
            "doctor is already running under sandbox-exec; the sandboxed pass would "
            "compose two profiles and is suppressed. Rerun outside the sandbox for the full 2x2 matrix."
        )
    elif layer_b_requested and not profile_exists:
        warnings.append(f"Layer B enabled but profile not found at {exp.layer_b.profile_path}; running baseline only.")

    # Run probe pass(es).
    try:
        baseline_json = probe.run_baseline(binary, exp)
    except probe.ProbeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return PROBE_ERROR

    if differential:
        try:
            sandboxed_json = probe.run_sandboxed(binary, exp, exp.layer_b.profile_path)
        except probe.ProbeError as exc:
            warnings.append(f"sandboxed pass failed ({exc}); falling back to baseline only.")
            differential = False

    # Classify.
    if differential:
        items = classify_differential(baseline_json, sandboxed_json, exp.required_categories)
        # Baseline classification still updates the cache grants/history.
        classify_baseline(baseline_json, cache, exp.required_categories)
        code = differential_exit_code(items)
    else:
        items = classify_baseline(baseline_json, cache, exp.required_categories)
        code = baseline_exit_code(items, strict=args.strict)

    # Persist cache (best-effort).
    try:
        cache.save()
    except OSError as exc:
        warnings.append(f"could not write probe cache: {exc}")

    profile_path = exp.layer_b.profile_path if differential else None

    if args.exit_zero:
        code = 0

    # Action modes that produce their own primary output.
    if args.mdm_profile:
        bundle = baseline_json.get("responsible_process", {}).get("bundle_id") or "com.apple.Terminal"
        xml, notes = mdm.build_mobileconfig(bundle)
        sys.stdout.write(xml)
        for n in notes:
            print(f"# {n}", file=sys.stderr)
        return code

    if args.suggest_sandbox_patch:
        if not differential:
            print("--suggest-sandbox-patch requires Layer B (enable security.layer_b or pass --with-sandbox).",
                  file=sys.stderr)
            return USAGE_ERROR
        diff = fixmod.suggest_patch(items, profile_path)
        if not diff:
            print("# No sandbox gaps — profile already covers all blocked categories.")
        else:
            sys.stdout.write(diff)
        return code

    # Report.
    if args.json:
        print(report.render_json(items, baseline_json, differential=differential,
                                 profile_path=profile_path, warnings=warnings, exit_code=code))
    else:
        print(report.render_human(items, baseline_json, differential=differential,
                                   profile_path=profile_path, warnings=warnings, exit_code=code))

    if args.fix:
        print()
        fixmod.run_fix(items)
    elif args.warmup:
        print("\n--warmup: the probe currently checks silently; use --fix to open the panes, "
              "or grant the not_determined categories from System Settings.", file=sys.stderr)

    return code


if __name__ == "__main__":
    raise SystemExit(main())
