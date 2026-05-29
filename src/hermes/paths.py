"""Canonical filesystem locations used across Hermes.

Two distinct roots (design.md Decision 20):

  * ``tool_root()``   — where the TOOL lives: ``bin/hermes-probe-tcc``,
    ``tools/probe-tcc/sandbox-rules.yaml``, the probe sidecar. Auto-detected;
    public ``hermes_setup`` repo.
  * ``config_root()`` — where the MANIFEST + secrets live: the capture/install/
    verify target. Resolved from a ``--manifest-dir`` override →
    ``HERMES_MANIFEST_DIR`` env → ``tool_root()`` (factory defaults). Private
    ``hermes_config`` repo.

Plus the ``~/.hermes/`` runtime directory (with a read-only-home fallback).
"""

from __future__ import annotations

import os
from pathlib import Path

_TOOL_MARKERS = ("manifest", "openspec", "bin")


def tool_root() -> Path:
    """Locate the hermes_setup (tool) repo root.

    1. ``HERMES_REPO_ROOT`` env, if set.
    2. Walk up from this file for a dir with ≥2 tool markers (manifest/, openspec/, bin/).
    3. Walk up from cwd with the same markers.
    4. Fall back to ``<this file>/../../..`` (the src-layout root).
    """
    env = os.environ.get("HERMES_REPO_ROOT")
    if env:
        return Path(env).expanduser().resolve()

    here = Path(__file__).resolve()
    for base in (here, Path.cwd().resolve()):
        for candidate in [base, *base.parents]:
            hits = sum(1 for m in _TOOL_MARKERS if (candidate / m).exists())
            if hits >= 2:
                return candidate

    return here.parents[2]


# Backwards-compatible alias (older call sites).
def repo_root() -> Path:
    return tool_root()


def config_root(override: str | Path | None = None) -> Path:
    """Locate the config root (the dir containing ``manifest/`` + ``secrets.env``).

    Resolution: explicit ``override`` (e.g. ``--manifest-dir``) →
    ``HERMES_MANIFEST_DIR`` env → ``tool_root()`` (factory defaults).
    """
    if override:
        return Path(override).expanduser().resolve()
    env = os.environ.get("HERMES_MANIFEST_DIR")
    if env:
        return Path(env).expanduser().resolve()
    return tool_root()


def hermes_home(create: bool = True) -> Path:
    """Return the Hermes runtime directory (``~/.hermes``, 0700; Library fallback)."""
    primary = Path.home() / ".hermes"
    fallback = Path.home() / "Library" / "Application Support" / "Hermes"

    if not create:
        return primary if primary.exists() else (fallback if fallback.exists() else primary)

    for candidate in (primary, fallback):
        try:
            candidate.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.chmod(candidate, 0o700)
            return candidate
        except OSError:
            continue
    return primary


def using_fallback_home() -> bool:
    return hermes_home(create=False).name == "Hermes"


def probe_cache_path() -> Path:
    return hermes_home() / "probe-cache.json"


def sandbox_profile_path() -> Path:
    """Default generated Seatbelt profile location (Layer B)."""
    return hermes_home() / "profile.sb"


# ---- tool-relative assets (always tool_root) ----


def probe_binary(cache_hint: str | None = None) -> Path | None:
    """Locate the probe binary: ``tool_root/bin`` → cache hint → PATH."""
    candidate = tool_root() / "bin" / "hermes-probe-tcc"
    if candidate.is_file() and os.access(candidate, os.X_OK):
        return candidate
    if cache_hint:
        hinted = Path(cache_hint)
        if hinted.is_file() and os.access(hinted, os.X_OK):
            return hinted
    from shutil import which

    found = which("hermes-probe-tcc")
    return Path(found) if found else None


def sandbox_rules_path() -> Path:
    return tool_root() / "tools" / "probe-tcc" / "sandbox-rules.yaml"


def probe_sidecar_path() -> Path:
    """`manifest/probe-tcc.yaml` is a tool artifact (the bundled binary's cdhash)."""
    return tool_root() / "manifest" / "probe-tcc.yaml"


# ---- config-relative paths (config_root) ----


def manifest_dir(config: str | Path | None = None) -> Path:
    return config_root(config) / "manifest"


def permissions_yaml_path(config: str | Path | None = None) -> Path:
    return manifest_dir(config) / "permissions.yaml"


def redact_config_path(config: str | Path | None = None) -> Path:
    return manifest_dir(config) / ".redact.yaml"


def secrets_env_path(config: str | Path | None = None) -> Path:
    return config_root(config) / "secrets.env"


def secrets_env_example_path(config: str | Path | None = None) -> Path:
    return config_root(config) / "secrets.env.example"


# ---- ~/.claude source layout (capture) ----

EXCLUDED_CLAUDE_NAMES: frozenset[str] = frozenset({
    "projects",
    "sessions",
    "session-env",
    "history.jsonl",
    "todos",
    "tasks",
    "telemetry",
    "debug",
    "cache",
    "paste-cache",
    "backups",
    "file-history",
    "shell-snapshots",
    "ide",
    "mcp-needs-auth-cache.json",
    "vscode-claude-status-cache.json",
    "plugin-catalog-cache.json",
    "settings.local.json",
})


def claude_dir(home: str | Path | None = None) -> Path:
    """The ~/.claude configuration directory (override home for tests)."""
    base = Path(home).expanduser() if home else Path.home()
    return base / ".claude"


def is_excluded_claude_path(name: str) -> bool:
    return name in EXCLUDED_CLAUDE_NAMES


# ---- $HOME templating (Decision 20) ----

HOME_TOKEN = "${HOME}"


def template_home(text: str, home: str | Path | None = None) -> str:
    """Rewrite the current home prefix to ``${HOME}`` (capture side)."""
    h = str(Path(home).expanduser() if home else Path.home())
    return text.replace(h, HOME_TOKEN)


def expand_home(text: str, home: str | Path | None = None) -> str:
    """Expand ``${HOME}`` back to the target home (install side)."""
    h = str(Path(home).expanduser() if home else Path.home())
    return text.replace(HOME_TOKEN, h)
