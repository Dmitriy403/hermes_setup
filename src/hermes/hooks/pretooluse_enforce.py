"""Layer A PreToolUse enforcement hook.

Reads the Claude Code PreToolUse payload from stdin, evaluates it against
``permissions.yaml``, and emits a permission decision. Registered by
``hermes install`` with the manifest's permissions path baked into the command.

Run as:  python3 -m hermes.hooks.pretooluse_enforce --permissions <path>
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .. import paths
from ..permissions import Permissions, evaluate


def _resolve_permissions_path(arg: str | None) -> str:
    if arg:
        return arg
    env = os.environ.get("HERMES_PERMISSIONS")
    if env:
        return env
    return str(paths.permissions_yaml_path())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hermes-pretooluse-enforce")
    parser.add_argument("--permissions", help="path to permissions.yaml")
    args, _ = parser.parse_known_args(argv)

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        # Malformed payload: do not block (fail-open for availability).
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": "hermes: unreadable hook payload, allowing",
        }}))
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}

    perms = Permissions.load(_resolve_permissions_path(args.permissions))
    decision = evaluate(perms, tool_name, tool_input)

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision.action,
        "permissionDecisionReason": f"hermes Layer A: {decision.reason}",
    }}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
