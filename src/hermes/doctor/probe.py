"""Invoke the probe binary and read manifest-derived expectations.

The probe is a dumb collector: doctor passes it everything it needs via CLI
flags and never lets it read the manifest. This module also owns Layer B
detection (whether to run a sandboxed pass) and nested-sandbox detection
(refuse to nest ``sandbox-exec``).
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import paths

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


class ProbeError(Exception):
    """Raised when the probe binary is missing or fails to produce JSON."""


# ---- manifest reading (doctor is the sole consumer) ----


@dataclass
class LayerB:
    enabled: bool = False
    profile_path: str | None = None


@dataclass
class Expectations:
    required_categories: set[str] = field(default_factory=set)
    automation_targets: list[str] = field(default_factory=list)
    expect_files: list[str] = field(default_factory=list)
    layer_b: LayerB = field(default_factory=LayerB)


def load_permissions() -> dict[str, Any]:
    path = paths.permissions_yaml_path()
    if not path.exists() or yaml is None:
        return {}
    try:
        return yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {}


def expectations(with_sandbox: str | None = None) -> Expectations:
    """Derive the categories/targets/files/Layer-B settings from permissions.yaml."""
    perms = load_permissions()
    tcc = perms.get("tcc", {}) if isinstance(perms, dict) else {}
    exp = Expectations()

    for category in ("screen-recording", "accessibility", "automation",
                     "full-disk-access", "microphone", "camera", "input-monitoring"):
        if category in tcc:
            exp.required_categories.add(category.replace("-", "_"))

    automation = tcc.get("automation", {})
    for target in (automation.get("targets", []) if isinstance(automation, dict) else []):
        bid = target.get("bundle-id") if isinstance(target, dict) else None
        if bid:
            exp.automation_targets.append(bid)

    for entry in tcc.get("files", []):
        if isinstance(entry, dict) and entry.get("path"):
            exp.required_categories.add("files")
            exp.expect_files.append(entry["path"])

    security = perms.get("security", {}) if isinstance(perms, dict) else {}
    lb = security.get("layer_b", {}) if isinstance(security, dict) else {}
    profile = lb.get("profile_path") or str(paths.sandbox_profile_path())
    exp.layer_b = LayerB(enabled=bool(lb.get("enabled", False)),
                         profile_path=os.path.expanduser(profile))

    # An explicit --with-sandbox overrides the manifest's Layer B config.
    if with_sandbox:
        exp.layer_b = LayerB(enabled=True, profile_path=os.path.expanduser(with_sandbox))

    return exp


# ---- nested-sandbox detection ----


def _parent_chain() -> list[tuple[int, str]]:
    chain: list[tuple[int, str]] = []
    pid = os.getpid()
    for _ in range(50):
        try:
            out = subprocess.run(
                ["ps", "-o", "ppid=,comm=", "-p", str(pid)],
                capture_output=True, text=True, timeout=2,
            )
        except Exception:
            break
        line = out.stdout.strip()
        if not line:
            break
        parts = line.split(None, 1)
        if len(parts) < 2:
            break
        try:
            ppid = int(parts[0])
        except ValueError:
            break
        comm = parts[1]
        chain.append((pid, comm))
        if ppid <= 1 or ppid == pid:
            break
        pid = ppid
    return chain


def _libsandbox_check() -> bool | None:
    """Use libSystem's sandbox_check(getpid(), NULL, 0) — returns 1 when the
    current process is sandboxed. Returns None if the symbol is unavailable.

    This is the reliable signal: `sandbox-exec` exec-replaces itself, so it
    never appears in the parent chain and sets no environment variable.
    """
    import ctypes

    try:
        libc = ctypes.CDLL("/usr/lib/libSystem.dylib")
        fn = libc.sandbox_check
        fn.restype = ctypes.c_int
        fn.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        return fn(os.getpid(), None, 0) > 0
    except (OSError, AttributeError, ValueError):
        return None


def doctor_is_sandboxed() -> bool:
    """True if doctor itself is running under a sandbox."""
    checked = _libsandbox_check()
    if checked is not None:
        return checked
    # Fallbacks for the rare case libsandbox is unavailable.
    if os.environ.get("SANDBOX_PROFILE"):
        return True
    return any("sandbox-exec" in comm for _, comm in _parent_chain())


# ---- probe invocation ----


def _run(cmd: list[str], extra_env: dict[str, str] | None = None) -> dict[str, Any]:
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20, env=env)
    except FileNotFoundError as exc:
        raise ProbeError(f"could not execute probe: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ProbeError("probe timed out after 20s") from exc

    if proc.returncode == -9 or proc.returncode == 137:
        raise ProbeError(
            "probe was killed by macOS (SIGKILL) with no output. The most "
            "common cause is a missing Info.plist Usage Description key for a "
            "newly added category. Add the NSXxxUsageDescription key to "
            "tools/probe-tcc/Info.plist and rebuild."
        )
    if not proc.stdout.strip():
        raise ProbeError(
            f"probe produced no JSON output (exit {proc.returncode}); stderr: {proc.stderr.strip()[:200]}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"probe output was not valid JSON: {exc}") from exc


def run_baseline(binary: Path, exp: Expectations) -> dict[str, Any]:
    cmd = [str(binary), "--json"]
    if exp.automation_targets:
        cmd.append("--automation-targets=" + ",".join(exp.automation_targets))
    if exp.expect_files:
        cmd.append("--expect-files=" + ",".join(exp.expect_files))
    return _run(cmd)


def run_sandboxed(binary: Path, exp: Expectations, profile: str) -> dict[str, Any]:
    cmd = ["sandbox-exec", "-f", profile, str(binary), "--self-test", "--json"]
    if exp.automation_targets:
        cmd.append("--automation-targets=" + ",".join(exp.automation_targets))
    if exp.expect_files:
        cmd.append("--expect-files=" + ",".join(exp.expect_files))
    return _run(cmd, extra_env={"HERMES_SANDBOX_PROFILE": profile})


def resolve_binary(cache_hint: str | None) -> Path:
    binary = paths.probe_binary(cache_hint=cache_hint)
    if binary is None:
        raise ProbeError(
            "probe binary not found at bin/hermes-probe-tcc. "
            "Run tools/probe-tcc/build.sh, then copy build/hermes-probe-tcc to bin/."
        )
    return binary
