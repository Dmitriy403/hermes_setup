"""`hermes capture` — scan the current machine and write the manifest.

Non-destructive: only reads ~/.claude/ and writes inside the repo's
manifest/ tree. Secrets are redacted (see redact.py) and ephemeral paths
(see paths.EXCLUDED_CLAUDE_NAMES) are never read.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import re

from . import paths
from .manifest import Manifest, McpServer, PluginEntry, SkillEntry
from .redact import Redactor

try:
    import yaml as _yaml
except ImportError:  # pragma: no cover
    _yaml = None

COMPONENTS = ("claude_md", "settings", "keybindings", "commands",
              "skills", "plugins", "mcp", "hooks")


@dataclass
class CaptureResult:
    manifest: Manifest
    redactor: Redactor
    actions: list[str] = field(default_factory=list)


def _selected(component: str, only: list[str] | None, skip: list[str] | None) -> bool:
    if only:
        return component in only
    if skip:
        return component not in skip
    return True


def _claude_version() -> str | None:
    try:
        out = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    # e.g. "1.2.3 (Claude Code)" -> "1.2.3"
    return out.stdout.strip().split()[0] if out.stdout.strip() else None


# ---- per-component capture ----


def capture_claude_md(claude: Path, mdir: Path, *, dry_run: bool, log: list[str]) -> bool:
    src = claude / "CLAUDE.md"
    if not src.exists():
        return False
    log.append(f"copy {src} -> manifest/CLAUDE.md")
    if not dry_run:
        shutil.copy2(src, mdir / "CLAUDE.md")
    return True


def capture_settings(claude: Path, mdir: Path, redactor: Redactor, *, dry_run: bool,
                     log: list[str], home: str | Path | None = None) -> tuple[bool, dict[str, Any]]:
    src = claude / "settings.json"
    if not src.exists():
        return False, {}
    data = json.loads(src.read_text())
    redacted = redactor.redact_json(data)
    pruned = _prune_permissions(redacted, log)
    redacted = pruned
    log.append(f"copy {src} -> manifest/settings.json (redacted, $HOME templated)")
    if not dry_run:
        text = json.dumps(redacted, indent=2, sort_keys=True) + "\n"
        text = paths.template_home(text, home)  # /Users/me/... -> ${HOME}/...
        (mdir / "settings.json").write_text(text)
    return True, data  # return the UN-redacted parse for mcp/hooks extraction


def capture_keybindings(claude: Path, mdir: Path, *, dry_run: bool, log: list[str]) -> bool:
    src = claude / "keybindings.json"
    if not src.exists():
        return False
    log.append(f"copy {src} -> manifest/keybindings.json")
    if not dry_run:
        shutil.copy2(src, mdir / "keybindings.json")
    return True


def capture_commands(claude: Path, mdir: Path, *, dry_run: bool, log: list[str]) -> list[str]:
    src = claude / "commands"
    if not src.is_dir():
        return []
    names: list[str] = []
    dst = mdir / "commands"
    for entry in sorted(src.iterdir()):
        if entry.name.startswith("."):
            continue
        names.append(entry.name)
        log.append(f"copy command {entry.name}")
        if not dry_run:
            dst.mkdir(parents=True, exist_ok=True)
            if entry.is_dir():
                shutil.copytree(entry, dst / entry.name, dirs_exist_ok=True)
            else:
                shutil.copy2(entry, dst / entry.name)
    return names


def _git_origin(skill_dir: Path) -> tuple[str | None, str | None]:
    try:
        repo = subprocess.run(["git", "-C", str(skill_dir), "remote", "get-url", "origin"],
                              capture_output=True, text=True, timeout=10)
        ref = subprocess.run(["git", "-C", str(skill_dir), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        repo_url = repo.stdout.strip() if repo.returncode == 0 else None
        head = ref.stdout.strip() if ref.returncode == 0 else None
        return repo_url, head
    except (FileNotFoundError, subprocess.SubprocessError):
        return None, None


def capture_skills(claude: Path, mdir: Path, *, dry_run: bool, log: list[str]) -> list[SkillEntry]:
    src = claude / "skills"
    if not src.is_dir():
        return []
    entries: list[SkillEntry] = []
    for skill_dir in sorted(src.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("."):
            continue
        name = skill_dir.name
        if (skill_dir / ".git").exists():
            repo, ref = _git_origin(skill_dir)
            entries.append(SkillEntry(name=name, source="git", repo=repo, ref=ref))
            log.append(f"skill {name}: git ({repo or 'unknown remote'})")
        else:
            entries.append(SkillEntry(name=name, source="local"))
            log.append(f"skill {name}: local (copying files)")
            if not dry_run:
                dst = mdir / "skills" / name / "files"
                dst.mkdir(parents=True, exist_ok=True)
                shutil.copytree(skill_dir, dst, dirs_exist_ok=True)
    return entries


def capture_plugins(claude: Path, *, log: list[str]) -> list[PluginEntry]:
    installed = claude / "plugins" / "installed_plugins.json"
    if not installed.exists():
        return []
    data = json.loads(installed.read_text())
    plugins = data.get("plugins", {}) or {}
    entries: list[PluginEntry] = []
    for full_name, installs in plugins.items():
        # "name@marketplace"
        if "@" in full_name:
            name, marketplace = full_name.split("@", 1)
        else:
            name, marketplace = full_name, None
        version = None
        if isinstance(installs, list) and installs and isinstance(installs[0], dict):
            version = installs[0].get("version")
        entries.append(PluginEntry(name=name, marketplace=marketplace, version=version))
        log.append(f"plugin {name}@{marketplace} {version or ''}".strip())
    return entries


def capture_mcp(settings: dict[str, Any], redactor: Redactor, *, log: list[str],
                home: str | Path | None = None) -> list[McpServer]:
    servers_cfg = settings.get("mcpServers", {}) or {}
    out: list[McpServer] = []
    for name, cfg in servers_cfg.items():
        if not isinstance(cfg, dict):
            continue
        redacted_env = redactor.redact_mapping(cfg.get("env", {}) or {})
        out.append(McpServer(
            name=name,
            command=paths.template_home(cfg.get("command", ""), home),
            args=[paths.template_home(a, home) for a in (cfg.get("args", []) or [])],
            env={k: paths.template_home(v, home) if isinstance(v, str) else v
                 for k, v in redacted_env.items()},
        ))
        log.append(f"mcp server {name} (env redacted, $HOME templated)")
    return out


def capture_hooks(claude: Path, mdir: Path, *, dry_run: bool, log: list[str]) -> list[str]:
    src = claude / "hooks"
    if not src.is_dir():
        return []
    names: list[str] = []
    dst = mdir / "hooks"
    for entry in sorted(src.iterdir()):
        if entry.name.startswith("."):
            continue
        names.append(entry.name)
        log.append(f"copy hook {entry.name}")
        if not dry_run:
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(entry, dst / entry.name)
    return names


# ---- orchestrator ----


def capture(
    config_root: str | Path | None = None,
    home: str | Path | None = None,
    *,
    only: list[str] | None = None,
    skip: list[str] | None = None,
    dry_run: bool = False,
) -> CaptureResult:
    root = Path(config_root) if config_root else paths.config_root()
    claude = paths.claude_dir(home)
    mdir = root / "manifest"
    if not dry_run:
        mdir.mkdir(parents=True, exist_ok=True)

    redactor = Redactor.from_config(root / "manifest" / ".redact.yaml")
    log: list[str] = []

    manifest = Manifest(claude_version=_claude_version())

    settings_data: dict[str, Any] = {}
    if _selected("settings", only, skip):
        manifest.has_settings, settings_data = capture_settings(
            claude, mdir, redactor, dry_run=dry_run, log=log, home=home)
    if _selected("claude_md", only, skip):
        manifest.has_claude_md = capture_claude_md(claude, mdir, dry_run=dry_run, log=log)
    if _selected("keybindings", only, skip):
        manifest.has_keybindings = capture_keybindings(claude, mdir, dry_run=dry_run, log=log)
    if _selected("commands", only, skip):
        manifest.commands = capture_commands(claude, mdir, dry_run=dry_run, log=log)
    if _selected("skills", only, skip):
        manifest.skills = capture_skills(claude, mdir, dry_run=dry_run, log=log)
    if _selected("plugins", only, skip):
        manifest.plugins = capture_plugins(claude, log=log)
    if _selected("mcp", only, skip):
        manifest.mcp_servers = capture_mcp(settings_data, redactor, log=log, home=home)
    if _selected("hooks", only, skip):
        manifest.hooks = capture_hooks(claude, mdir, dry_run=dry_run, log=log)

    if not dry_run:
        manifest.save(root)
        # secrets.env.example (§3.9)
        example_path = root / "secrets.env.example"
        example_path.write_text(redactor.secrets_env_example())
        log.append(f"wrote {example_path}")
        # Permissions overlay (§3/§14.6, option C): enrich an existing
        # permissions.yaml with discovered facts; never remove anything.
        overlay_permissions(root, settings_data, manifest.mcp_servers, log=log)

    return CaptureResult(manifest=manifest, redactor=redactor, actions=log)


# Auto-accumulated one-shot grants that add no value to a reproducible manifest
# (e.g. a `mkdir -p` that a skill install requested once). Pruned on capture.
_TRANSIENT_ALLOW_RE = re.compile(r"^Bash\(mkdir\b")


def _prune_permissions(settings: dict[str, Any], log: list[str]) -> dict[str, Any]:
    perms = settings.get("permissions")
    if not isinstance(perms, dict):
        return settings
    allow = perms.get("allow")
    if not isinstance(allow, list):
        return settings
    kept = [a for a in allow if not (isinstance(a, str) and _TRANSIENT_ALLOW_RE.match(a))]
    dropped = len(allow) - len(kept)
    if dropped:
        perms["allow"] = kept
        log.append(f"pruned {dropped} transient permission grant(s) (Bash(mkdir …))")
    return settings


_WEBFETCH_DOMAIN_RE = re.compile(r"WebFetch\(domain:([^)]+)\)")


def overlay_permissions(root: Path, settings: dict[str, Any],
                        mcp_servers: list[McpServer], *, log: list[str]) -> None:
    """Add discovered network domains + MCP servers to an existing
    manifest/permissions.yaml. Additive only — preserves the starter profile.
    """
    perms_path = root / "manifest" / "permissions.yaml"
    if not perms_path.exists() or _yaml is None:
        return
    perms = _yaml.safe_load(perms_path.read_text()) or {}
    changed = False

    # WebFetch(domain:X) entries from settings.permissions.allow → network.domains
    allow = (settings.get("permissions", {}) or {}).get("allow", []) or []
    discovered_domains = []
    for entry in allow:
        if isinstance(entry, str):
            m = _WEBFETCH_DOMAIN_RE.search(entry)
            if m:
                discovered_domains.append(m.group(1))
    if discovered_domains:
        net = perms.setdefault("network", {})
        domains = net.setdefault("domains", [])
        for d in discovered_domains:
            if d not in domains:
                domains.append(d)
                changed = True
                log.append(f"permissions overlay: +network.domain {d}")

    # captured MCP servers → mcp.enabled globs
    if mcp_servers:
        mcp = perms.setdefault("mcp", {})
        enabled = mcp.setdefault("enabled", [])
        for server in mcp_servers:
            glob = f"{server.name}.*"
            if glob not in enabled and server.name not in enabled:
                enabled.append(glob)
                changed = True
                log.append(f"permissions overlay: +mcp.enabled {glob}")

    if changed:
        perms_path.write_text(_yaml.safe_dump(perms, sort_keys=False, allow_unicode=True))
