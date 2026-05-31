"""A fake `claude` CLI for tests — implements just enough of `claude mcp`
(add / get / list / remove) to exercise hermes's `mcp_cli` adapter and
`step_mcp` without the real Claude Code binary.

It writes to ``$HOME/.claude.json`` the same way real claude does:
- ``-s user``  → top-level ``mcpServers``
- ``-s local`` / ``-s project`` → ``projects[<cwd>].mcpServers``

Tests point ``HERMES_CLAUDE_BIN`` at the written script and pass a temp HOME,
so registration never touches the real ~/.claude.json.
"""

from __future__ import annotations

import stat
from pathlib import Path

_SCRIPT = r'''#!/usr/bin/env python3
import json, os, sys


def _cfg():
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return os.path.join(home, ".claude.json")


def _load():
    try:
        with open(_cfg()) as fh:
            return json.load(fh)
    except (FileNotFoundError, ValueError):
        return {}


def _save(d):
    with open(_cfg(), "w") as fh:
        json.dump(d, fh, indent=2)


def _names(d):
    out = set((d.get("mcpServers") or {}).keys())
    for p in (d.get("projects") or {}).values():
        if isinstance(p, dict):
            out |= set((p.get("mcpServers") or {}).keys())
    return out


argv = sys.argv[1:]
if argv[:1] != ["mcp"]:
    sys.exit(0)
sub = argv[1] if len(argv) > 1 else ""
rest = argv[2:]

if sub == "add":
    scope = "local"
    name = command = None
    cmdargs, env = [], {}
    i = 0
    while i < len(rest):
        a = rest[i]
        if a in ("-s", "--scope"):
            scope = rest[i + 1]; i += 2
        elif a in ("-e", "--env"):
            k, _, v = rest[i + 1].partition("="); env[k] = v; i += 2
        elif a == "--":
            i += 1
        elif name is None:
            name = a; i += 1
        elif command is None:
            command = a; i += 1
        else:
            cmdargs.append(a); i += 1
    entry = {"command": command, "args": cmdargs, "env": env}
    d = _load()
    if scope == "user":
        d.setdefault("mcpServers", {})[name] = entry
    else:
        cwd = os.getcwd()
        d.setdefault("projects", {}).setdefault(cwd, {}).setdefault("mcpServers", {})[name] = entry
    _save(d)
    print("Added %s (%s)" % (name, scope))
    sys.exit(0)

if sub == "get":
    name = rest[-1] if rest else ""
    sys.exit(0 if name in _names(_load()) else 1)

if sub == "list":
    for n in sorted(_names(_load())):
        print("%s: connected" % n)
    sys.exit(0)

if sub == "remove":
    name = rest[-1] if rest else ""
    d = _load()
    (d.get("mcpServers") or {}).pop(name, None)
    for p in (d.get("projects") or {}).values():
        if isinstance(p, dict):
            (p.get("mcpServers") or {}).pop(name, None)
    _save(d)
    sys.exit(0)

sys.exit(0)
'''


def write_fake_claude(bindir: str | Path) -> str:
    """Write the fake claude script under bindir/claude and return its path."""
    bindir = Path(bindir)
    bindir.mkdir(parents=True, exist_ok=True)
    p = bindir / "claude"
    p.write_text(_SCRIPT)
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(p)
