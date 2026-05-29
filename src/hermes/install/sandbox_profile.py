"""Generate a deterministic Seatbelt (sandbox-exec) profile (Layer B).

The profile is derived from ``manifest/permissions.yaml`` plus the canonical
``tools/probe-tcc/sandbox-rules.yaml`` mapping. Output is byte-stable for a
given input (sorted within groups, no timestamps) so ``hermes verify`` can
detect drift and re-runs are no-ops.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .. import paths

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


def sandbox_rules_path() -> Path:
    return paths.sandbox_rules_path()  # tool_root — a tool asset


def load_sandbox_rules() -> dict[str, Any]:
    path = sandbox_rules_path()
    if not path.exists() or yaml is None:
        return {}
    return yaml.safe_load(path.read_text()) or {}


# ---- glob -> Seatbelt path translation ----


def _expand(pattern: str, home: str) -> str:
    if pattern.startswith("~"):
        return home + pattern[1:]
    return pattern


def _glob_to_regex(glob: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(glob):
        c = glob[i]
        if c == "*":
            if i + 1 < len(glob) and glob[i + 1] == "*":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
            i += 1
            continue
        if c in r".[]{}()+?^$|\\":
            out.append("\\" + c)
        else:
            out.append(c)
        i += 1
    return "".join(out)


def _path_clause(pattern: str, home: str) -> str:
    """Return a Seatbelt path filter clause: (subpath ...), (literal ...) or (regex ...)."""
    expanded = _expand(pattern, home)
    if "*" not in expanded:
        return f'(literal "{expanded}")'
    if expanded.endswith("/**"):
        return f'(subpath "{expanded[:-3]}")'
    # Anything else with a wildcard becomes an anchored regex.
    return f'(regex #"{_glob_to_regex(expanded)}$")'


# ---- profile generation ----

_PRELUDE = [
    "(version 1)",
    "(deny default)",
    '(import "/System/Library/Sandbox/Profiles/system.sb")',
]

_PROCESS_BASICS = [
    "(allow process-fork)",
    "(allow sysctl-read)",
    "(allow signal (target self))",
]


def generate(permissions: dict[str, Any], sandbox_rules: dict[str, Any], *, home: str | None = None) -> str:
    """Return the full Seatbelt profile text for the given permissions."""
    home = home or str(Path.home())
    perms = permissions or {}
    rules = sandbox_rules or {}

    lines: list[str] = []
    lines += _PRELUDE
    lines.append("")
    lines.append(";; --- process basics ---")
    lines += _PROCESS_BASICS

    fs = perms.get("filesystem", {}) or {}
    read = sorted(fs.get("read", []) or [])
    write = sorted(fs.get("write", []) or [])
    write_exec = sorted(fs.get("write-exec", []) or [])
    forbidden = sorted(fs.get("forbidden", []) or [])

    # read access: read + write + write-exec all need read.
    all_read = sorted(set(read) | set(write) | set(write_exec))
    if all_read:
        lines.append("")
        lines.append(";; --- filesystem: read ---")
        for p in all_read:
            lines.append(f"(allow file-read* {_path_clause(p, home)})")

    all_write = sorted(set(write) | set(write_exec))
    if all_write:
        lines.append("")
        lines.append(";; --- filesystem: write ---")
        for p in all_write:
            lines.append(f"(allow file-write* {_path_clause(p, home)})")

    if write_exec:
        lines.append("")
        lines.append(";; --- filesystem: exec ---")
        for p in sorted(write_exec):
            lines.append(f"(allow process-exec* {_path_clause(p, home)})")

    if forbidden:
        lines.append("")
        lines.append(";; --- filesystem: forbidden (explicit deny, defense-in-depth) ---")
        for p in forbidden:
            clause = _path_clause(p, home)
            lines.append(f"(deny file-read* {clause})")
            lines.append(f"(deny file-write* {clause})")

    # Shell: broad process-exec*. Fine-grained command policy is Layer A's job.
    shell = perms.get("shell", {}) or {}
    if shell.get("allow"):
        lines.append("")
        lines.append(";; --- shell exec (broad; command-level policy is enforced by the Layer A hook) ---")
        lines.append("(allow process-exec*)")

    # TCC categories.
    tcc = perms.get("tcc", {}) or {}
    cat_rules = rules.get("categories", {}) or {}
    emitted_simple: list[str] = []
    for manifest_key in tcc:
        norm = manifest_key.replace("-", "_")
        if norm in cat_rules:
            emitted_simple.append(norm)
    for norm in sorted(set(emitted_simple)):
        lines.append("")
        lines.append(f";; --- TCC: {norm} ---")
        for rule in cat_rules[norm]:
            lines.append(rule)

    # Automation (templated).
    automation = tcc.get("automation", {}) or {}
    targets = automation.get("targets", []) or []
    auto_rules = rules.get("automation", {}) or {}
    if targets and auto_rules:
        lines.append("")
        lines.append(";; --- TCC: automation ---")
        for rule in auto_rules.get("base", []) or []:
            lines.append(rule)
        bundle_ids = sorted(
            t.get("bundle-id") for t in targets if isinstance(t, dict) and t.get("bundle-id")
        )
        for bid in bundle_ids:
            for tmpl in auto_rules.get("per_target", []) or []:
                lines.append(tmpl.replace("{bundle_id}", bid))

    # Files (templated).
    files = tcc.get("files", []) or []
    files_rules = rules.get("files", {}) or {}
    if files and files_rules:
        lines.append("")
        lines.append(";; --- TCC: files ---")
        file_paths = sorted(
            _expand(f["path"], home) for f in files if isinstance(f, dict) and f.get("path")
        )
        for fp in file_paths:
            for tmpl in files_rules.get("per_path", []) or []:
                lines.append(tmpl.replace("{path}", fp))

    return "\n".join(lines) + "\n"


def generate_from_manifest(home: str | None = None, config: str | None = None) -> str:
    perms = {}
    path = paths.permissions_yaml_path(config)  # config_root — user's policy
    if path.exists() and yaml is not None:
        perms = yaml.safe_load(path.read_text()) or {}
    return generate(perms, load_sandbox_rules(), home=home)  # rules from tool_root
