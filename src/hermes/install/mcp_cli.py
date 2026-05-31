"""Thin adapter over the `claude mcp` CLI — the ONLY place hermes shells out
to register MCP servers.

Why this exists: Claude Code loads MCP servers from `~/.claude.json`
(written by `claude mcp add`, with user/project/local scopes) and from
project `.mcp.json` — NOT from `~/.claude/settings.json`. hermes v1 wrote
servers into settings.json's `mcpServers` map, which Claude Code silently
ignores, so every "installed" server was dead. This module registers them
through the supported interface instead.

All calls are isolated here so the CLI surface (flags, exit codes) is mocked
in exactly one place. The binary is resolved via `HERMES_CLAUDE_BIN` (a test /
override seam) then `which("claude")`; when neither resolves, callers get a
``None`` binary and are expected to fail soft.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from shutil import which


# Scopes Claude Code understands. `local` is per-project + private (default for
# polling servers — one poller, no Telegram 409); `user` is global / everywhere
# (default for non-polling servers); `project` writes a committable .mcp.json.
VALID_SCOPES = frozenset({"local", "user", "project"})


def claude_bin() -> str | None:
    """Resolve the claude CLI: explicit override first, then PATH."""
    return os.environ.get("HERMES_CLAUDE_BIN") or which("claude")


def manual_add_command(name: str, command: str, args: list[str],
                       env: dict[str, str], scope: str) -> str:
    """The exact `claude mcp add` line a user can run by hand (env VALUES
    omitted so we never echo secrets like a Telegram token)."""
    parts = ["claude", "mcp", "add", "-s", scope, name, command, *args]
    parts += [f"-e {k}=…" for k in env]
    return " ".join(parts)


@dataclass
class McpCli:
    """Bound to a target HOME and working dir so registration lands in the
    right `~/.claude.json` (and the right project for local/project scope)."""
    binary: str
    home: str
    cwd: str

    def _env(self) -> dict[str, str]:
        env = dict(os.environ)
        env["HOME"] = self.home
        return env

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self.binary, "mcp", *args],
            capture_output=True, text=True, timeout=30,
            env=self._env(), cwd=self.cwd,
        )

    def is_registered(self, name: str) -> bool:
        """True if `claude mcp get <name>` succeeds (already registered)."""
        try:
            return self._run("get", name).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def add(self, name: str, command: str, args: list[str],
            env: dict[str, str], scope: str) -> tuple[bool, str]:
        """Register a server. Returns (ok, message). Idempotent at the call
        site via is_registered(); this method always issues the add."""
        cli_args = ["add", "-s", scope, name, command, *args]
        for k, v in env.items():
            cli_args += ["-e", f"{k}={v}"]
        try:
            proc = self._run(*cli_args)
        except (OSError, subprocess.SubprocessError) as exc:
            return False, str(exc)
        if proc.returncode != 0:
            return False, (proc.stderr or proc.stdout).strip()[:200]
        return True, (proc.stdout or "").strip()
