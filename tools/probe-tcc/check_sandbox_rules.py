#!/usr/bin/env python3
"""Consistency check: the probe's Swift rule constants must match
sandbox-rules.yaml. Run in CI on every commit touching tools/probe-tcc/.

Both sides are normalized (template placeholders unified) and compared as
sets. Exits non-zero on any drift.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("pyyaml required", file=sys.stderr)
    sys.exit(2)

HERE = Path(__file__).resolve().parent
SWIFT = HERE / "Sources" / "SandboxRules.swift"
YAML = HERE / "sandbox-rules.yaml"

_PLACEHOLDER = "{X}"


def _normalize(rule: str) -> str:
    # Swift interpolation \(bundleID) / \(path) and yaml {bundle_id} / {path}
    # both collapse to a single placeholder token.
    rule = re.sub(r"\\\([A-Za-z_]+\)", _PLACEHOLDER, rule)
    rule = re.sub(r"\{[A-Za-z_]+\}", _PLACEHOLDER, rule)
    return rule.strip()


def swift_rules() -> set[str]:
    text = SWIFT.read_text()
    out: set[str] = set()
    # Match Swift string literals including escaped inner quotes (\"),
    # then keep the ones that are Seatbelt clauses and unescape them.
    for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', text):
        s = m.group(1).replace('\\"', '"')
        if s.startswith("(allow") or s.startswith("(deny"):
            out.add(_normalize(s))
    return out


def yaml_rules() -> set[str]:
    data = yaml.safe_load(YAML.read_text()) or {}
    out: set[str] = set()
    for rules in (data.get("categories", {}) or {}).values():
        for r in rules:
            out.add(_normalize(r))
    automation = data.get("automation", {}) or {}
    for r in automation.get("base", []) or []:
        out.add(_normalize(r))
    for r in automation.get("per_target", []) or []:
        out.add(_normalize(r))
    for r in (data.get("files", {}) or {}).get("per_path", []) or []:
        out.add(_normalize(r))
    return out


def main() -> int:
    swift = swift_rules()
    yml = yaml_rules()
    if swift == yml:
        print(f"OK — {len(swift)} rules match between SandboxRules.swift and sandbox-rules.yaml")
        return 0
    only_swift = swift - yml
    only_yaml = yml - swift
    print("DRIFT between SandboxRules.swift and sandbox-rules.yaml:", file=sys.stderr)
    for r in sorted(only_swift):
        print(f"  only in Swift: {r}", file=sys.stderr)
    for r in sorted(only_yaml):
        print(f"  only in YAML:  {r}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
