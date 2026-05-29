"""Tests for Layer A policy evaluation + the PreToolUse hook."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hermes.permissions import Permissions, evaluate  # noqa: E402

_SRC = str(Path(__file__).resolve().parents[1] / "src")

_PERMS_YAML = """
schema_version: 1
filesystem:
  write-exec: ["~/projects/**"]
  write: ["~/Documents/**"]
  read: ["~/Downloads/**"]
  forbidden:
    - "~/.ssh/**"
    - "**/*.pem"
    - "**/secrets.env"
shell:
  allow: [git, python3, ls]
  ask: [curl, rm]
  deny:
    - sudo
    - "rm -rf /"
network:
  domains: [gitcode.com, api.anthropic.com]
  default: ask
mcp:
  enabled: ["mempalace.*"]
  disabled: ["evil.*"]
"""


def _perms() -> Permissions:
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "permissions.yaml"
        p.write_text(_PERMS_YAML)
        return Permissions.load(p)


def test_write_to_forbidden_is_denied():
    perms = _perms()
    home = str(Path.home())
    assert evaluate(perms, "Write", {"file_path": f"{home}/.ssh/id_rsa"}).action == "deny"
    assert evaluate(perms, "Write", {"file_path": f"{home}/work/key.pem"}).action == "deny"
    assert evaluate(perms, "Edit", {"file_path": f"{home}/app/secrets.env"}).action == "deny"


def test_write_to_allowed_is_allowed():
    perms = _perms()
    home = str(Path.home())
    assert evaluate(perms, "Write", {"file_path": f"{home}/projects/foo/main.py"}).action == "allow"
    assert evaluate(perms, "Write", {"file_path": f"{home}/Documents/notes.md"}).action == "allow"


def test_read_forbidden_denied():
    perms = _perms()
    home = str(Path.home())
    assert evaluate(perms, "Read", {"file_path": f"{home}/.ssh/config"}).action == "deny"


def test_bash_deny_ask_allow():
    perms = _perms()
    assert evaluate(perms, "Bash", {"command": "sudo rm x"}).action == "deny"
    assert evaluate(perms, "Bash", {"command": "rm -rf /"}).action == "deny"
    assert evaluate(perms, "Bash", {"command": "curl https://x"}).action == "ask"
    assert evaluate(perms, "Bash", {"command": "rm foo.txt"}).action == "ask"
    assert evaluate(perms, "Bash", {"command": "git status"}).action == "allow"
    # env-var prefix is skipped to find the real command
    assert evaluate(perms, "Bash", {"command": "FOO=bar git status"}).action == "allow"
    # unlisted command → allow-by-default
    assert evaluate(perms, "Bash", {"command": "jq ."}).action == "allow"


def test_webfetch_domain_policy():
    perms = _perms()
    assert evaluate(perms, "WebFetch", {"url": "https://gitcode.com/x"}).action == "allow"
    assert evaluate(perms, "WebFetch", {"url": "https://api.anthropic.com/v1"}).action == "allow"
    # subdomain of an allowed domain
    assert evaluate(perms, "WebFetch", {"url": "https://raw.gitcode.com/x"}).action == "allow"
    # unlisted → default ask
    assert evaluate(perms, "WebFetch", {"url": "https://evil.example.com"}).action == "ask"


def test_mcp_policy():
    perms = _perms()
    assert evaluate(perms, "mcp__mempalace__search", {}).action == "allow"
    assert evaluate(perms, "mcp__evil__exfiltrate", {}).action == "deny"
    # not in enabled list → ask (enabled list is non-empty)
    assert evaluate(perms, "mcp__unknown__tool", {}).action == "ask"


def test_ungoverned_tool_allowed():
    perms = _perms()
    assert evaluate(perms, "Glob", {"pattern": "**/*.py"}).action == "allow"


def test_hook_subprocess_denies_forbidden_write():
    home = str(Path.home())
    with tempfile.TemporaryDirectory() as d:
        perms_path = Path(d) / "permissions.yaml"
        perms_path.write_text(_PERMS_YAML)
        payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": f"{home}/.ssh/id_rsa"}})
        proc = subprocess.run(
            [sys.executable, "-m", "hermes.hooks.pretooluse_enforce", "--permissions", str(perms_path)],
            input=payload, capture_output=True, text=True,
            env={"PYTHONPATH": _SRC, "PATH": "/usr/bin:/bin"},
        )
        assert proc.returncode == 0, proc.stderr
        out = json.loads(proc.stdout)
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "forbidden" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_hook_subprocess_allows_normal_write():
    home = str(Path.home())
    with tempfile.TemporaryDirectory() as d:
        perms_path = Path(d) / "permissions.yaml"
        perms_path.write_text(_PERMS_YAML)
        payload = json.dumps({"tool_name": "Write", "tool_input": {"file_path": f"{home}/projects/x.py"}})
        proc = subprocess.run(
            [sys.executable, "-m", "hermes.hooks.pretooluse_enforce", "--permissions", str(perms_path)],
            input=payload, capture_output=True, text=True,
            env={"PYTHONPATH": _SRC, "PATH": "/usr/bin:/bin"},
        )
        out = json.loads(proc.stdout)
        assert out["hookSpecificOutput"]["permissionDecision"] == "allow"


def _run_standalone() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL {fn.__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_standalone())
