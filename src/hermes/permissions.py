"""Layer A policy model and evaluation.

Loads ``manifest/permissions.yaml`` and decides allow / ask / deny for a tool
call. v1 posture is allow-by-default + targeted denylist (see design.md
Decision 14 / Open Q10): the ``filesystem.forbidden`` and ``shell.deny`` lists
are the hard boundaries; ``network`` is gated by ``network.default``.

Kept separate from manifest.py so the PreToolUse hook can import just this
(small, dependency-light) module.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


@dataclass
class Decision:
    action: str  # "allow" | "ask" | "deny"
    reason: str


@dataclass
class Permissions:
    fs_write_exec: list[str] = field(default_factory=list)
    fs_write: list[str] = field(default_factory=list)
    fs_read: list[str] = field(default_factory=list)
    fs_forbidden: list[str] = field(default_factory=list)
    shell_allow: list[str] = field(default_factory=list)
    shell_ask: list[str] = field(default_factory=list)
    shell_deny: list[str] = field(default_factory=list)
    network_domains: list[str] = field(default_factory=list)
    network_default: str = "ask"
    mcp_enabled: list[str] = field(default_factory=list)
    mcp_disabled: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "Permissions":
        if yaml is None:
            return cls()
        p = Path(path)
        if not p.exists():
            return cls()
        data = yaml.safe_load(p.read_text()) or {}
        fs = data.get("filesystem", {}) or {}
        shell = data.get("shell", {}) or {}
        net = data.get("network", {}) or {}
        mcp = data.get("mcp", {}) or {}
        return cls(
            fs_write_exec=list(fs.get("write-exec", []) or []),
            fs_write=list(fs.get("write", []) or []),
            fs_read=list(fs.get("read", []) or []),
            fs_forbidden=list(fs.get("forbidden", []) or []),
            shell_allow=list(shell.get("allow", []) or []),
            shell_ask=list(shell.get("ask", []) or []),
            shell_deny=list(shell.get("deny", []) or []),
            network_domains=list(net.get("domains", []) or []),
            network_default=net.get("default", "ask"),
            mcp_enabled=list(mcp.get("enabled", []) or []),
            mcp_disabled=list(mcp.get("disabled", []) or []),
        )


# ---- glob / path matching ----


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


def _expand(pattern: str) -> str:
    if pattern.startswith("~"):
        return os.path.expanduser(pattern)
    return pattern


def path_matches(path: str, pattern: str) -> bool:
    """True if an absolute path matches a glob pattern (`**` spans `/`)."""
    if not path:
        return False
    target = os.path.abspath(os.path.expanduser(path))
    pat = _expand(pattern)
    # "dir/**" should also match "dir" itself.
    if pat.endswith("/**"):
        prefix = pat[:-3]
        if target == prefix or target.startswith(prefix + "/"):
            return True
    regex = _glob_to_regex(pat)
    return re.fullmatch(regex, target) is not None


def _any_match(path: str, patterns: list[str]) -> bool:
    return any(path_matches(path, p) for p in patterns)


# ---- per-tool evaluation ----


def _leading_token(command: str) -> str:
    command = command.strip()
    if not command:
        return ""
    first = command.split()[0]
    # env-var prefixes like FOO=bar cmd → skip to the command
    while "=" in first and not first.startswith("/") and first.split("=")[0].isidentifier():
        rest = command.split(None, 1)
        if len(rest) < 2:
            return ""
        command = rest[1]
        first = command.split()[0]
    return os.path.basename(first)


def _eval_fs(perms: Permissions, path: str | None, *, verb: str) -> Decision:
    if not path:
        return Decision("allow", f"{verb}: no path in payload")
    if _any_match(path, perms.fs_forbidden):
        return Decision("deny", f"{verb} blocked: {path} is in filesystem.forbidden")
    return Decision("allow", f"{verb} allowed: {path} not forbidden")


def _eval_bash(perms: Permissions, command: str) -> Decision:
    if not command:
        return Decision("allow", "empty command")
    # Hard deny: explicit dangerous patterns (multi-word entries) or denied tokens.
    for pat in perms.shell_deny:
        if " " in pat or "*" in pat:
            if re.search(_glob_to_regex(pat), command):
                return Decision("deny", f"command matches shell.deny pattern: {pat}")
    token = _leading_token(command)
    if token in perms.shell_deny:
        return Decision("deny", f"command '{token}' is in shell.deny")
    if token in perms.shell_ask:
        return Decision("ask", f"command '{token}' requires confirmation (shell.ask)")
    if token in perms.shell_allow:
        return Decision("allow", f"command '{token}' is in shell.allow")
    return Decision("allow", f"command '{token}' not restricted (allow-by-default)")


def _domain_of(url: str) -> str:
    m = re.match(r"[a-zA-Z][a-zA-Z0-9+.\-]*://([^/:]+)", url)
    if m:
        return m.group(1).lower()
    return url.split("/")[0].lower()


def _eval_web(perms: Permissions, url: str) -> Decision:
    if not url:
        return Decision("allow", "no url")
    domain = _domain_of(url)
    for allowed in perms.network_domains:
        if domain == allowed.lower() or domain.endswith("." + allowed.lower()):
            return Decision("allow", f"{domain} in network.domains")
    default = perms.network_default.lower()
    if default == "allow":
        return Decision("allow", f"{domain} not listed; network.default=allow")
    if default == "deny":
        return Decision("deny", f"{domain} not in network.domains; network.default=deny")
    return Decision("ask", f"{domain} not in network.domains; network.default=ask")


def _mcp_server(tool_name: str) -> str:
    # mcp__<server>__<tool>
    parts = tool_name.split("__")
    return parts[1] if len(parts) >= 2 else ""


def _glob_name_match(name: str, patterns: list[str]) -> bool:
    for p in patterns:
        rx = "^" + re.escape(p).replace(r"\*", ".*") + "$"
        if re.match(rx, name) or re.match(rx, name + ".") or p == name:
            return True
        # allow "server.*" to match bare "server"
        if p.endswith(".*") and name == p[:-2]:
            return True
    return False


def _eval_mcp(perms: Permissions, tool_name: str) -> Decision:
    server = _mcp_server(tool_name)
    if _glob_name_match(server, perms.mcp_disabled):
        return Decision("deny", f"mcp server '{server}' is disabled")
    if perms.mcp_enabled and not _glob_name_match(server, perms.mcp_enabled):
        return Decision("ask", f"mcp server '{server}' not in mcp.enabled")
    return Decision("allow", f"mcp server '{server}' permitted")


def render_capabilities(perms: Permissions) -> str:
    """Human-readable summary of the effective Layer A policy."""
    def block(title: str, items: list[str], glyph: str) -> list[str]:
        if not items:
            return []
        out = [f"  {glyph} {title}"]
        for it in items:
            out.append(f"      {it}")
        return out

    lines = ["Hermes capabilities (Layer A policy)", ""]
    lines.append("FILESYSTEM")
    lines += block("write+exec", perms.fs_write_exec, "rwx")
    lines += block("write", perms.fs_write, "rw-")
    lines += block("read", perms.fs_read, "r--")
    lines += block("forbidden", perms.fs_forbidden, "DENY")
    lines.append("")
    lines.append("SHELL")
    lines += block("allow", perms.shell_allow, "ok")
    lines += block("ask", perms.shell_ask, "ask")
    lines += block("deny", perms.shell_deny, "DENY")
    lines.append("")
    lines.append("NETWORK")
    lines += block("domains", perms.network_domains, "ok")
    lines.append(f"  default: {perms.network_default}")
    lines.append("")
    lines.append("MCP")
    lines += block("enabled", perms.mcp_enabled, "ok")
    lines += block("disabled", perms.mcp_disabled, "DENY")
    return "\n".join(lines)


def evaluate(perms: Permissions, tool_name: str, tool_input: dict[str, Any]) -> Decision:
    if tool_name in ("Write", "Edit", "MultiEdit"):
        return _eval_fs(perms, tool_input.get("file_path"), verb=tool_name)
    if tool_name == "NotebookEdit":
        return _eval_fs(perms, tool_input.get("notebook_path"), verb=tool_name)
    if tool_name == "Read":
        return _eval_fs(perms, tool_input.get("file_path"), verb="Read")
    if tool_name == "Bash":
        return _eval_bash(perms, tool_input.get("command", ""))
    if tool_name == "WebFetch":
        return _eval_web(perms, tool_input.get("url", ""))
    if tool_name.startswith("mcp__"):
        return _eval_mcp(perms, tool_name)
    return Decision("allow", "tool not governed by Layer A")
