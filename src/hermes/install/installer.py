"""`hermes install` — replay the manifest onto a target ~/.claude/.

Fail-fast on missing secrets (before any write), idempotent (unchanged
components are skipped), and dry-run capable (every mutation goes through a
single Mutator). Verbatim files are written via staging temp + atomic
rename. MCP servers are written into settings.json's `mcpServers` map for
v1 (Decision: avoids a hard dependency on `claude mcp add`).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from shutil import which
from typing import Any

from .. import paths, plugins_registry
from ..manifest import Manifest, parse_secrets_env, resolve_manifest_env
from . import launchd as tool_launchd
from . import sandbox_profile

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


class InstallError(Exception):
    """Raised on a fatal install precondition (e.g. missing secrets)."""


# ---- mutation helper (§4.8) ----


@dataclass
class Mutator:
    dry_run: bool
    log: list[str] = field(default_factory=list)

    def write_text(self, path: Path, content: str, *, mode: int | None = None, label: str | None = None) -> None:
        name = label or str(path)
        if path.exists() and path.read_text() == content:
            self.log.append(f"unchanged: {name}")
            return
        verb = "would write" if self.dry_run else "write"
        self.log.append(f"{verb}: {name}")
        if self.dry_run:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".hermes-stage.")
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(content)
            if mode is not None:
                os.chmod(tmp, mode)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def copy_file(self, src: Path, dst: Path, *, label: str | None = None) -> None:
        name = label or str(dst)
        if dst.exists() and src.exists() and dst.read_bytes() == src.read_bytes():
            self.log.append(f"unchanged: {name}")
            return
        verb = "would copy" if self.dry_run else "copy"
        self.log.append(f"{verb}: {name}")
        if not self.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    def copytree(self, src: Path, dst: Path, *, label: str | None = None) -> None:
        name = label or str(dst)
        verb = "would copy tree" if self.dry_run else "copy tree"
        self.log.append(f"{verb}: {name}")
        if not self.dry_run:
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dst, dirs_exist_ok=True)

    def mkdir(self, path: Path, *, mode: int = 0o755) -> None:
        if path.exists():
            return
        self.log.append(f"{'would mkdir' if self.dry_run else 'mkdir'}: {path}")
        if not self.dry_run:
            path.mkdir(mode=mode, parents=True, exist_ok=True)
            os.chmod(path, mode)

    def run(self, cmd: list[str], *, label: str | None = None) -> bool:
        name = label or " ".join(cmd)
        verb = "would run" if self.dry_run else "run"
        self.log.append(f"{verb}: {name}")
        if self.dry_run:
            return True
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        except (FileNotFoundError, subprocess.SubprocessError) as exc:
            self.log.append(f"  ! command failed: {exc}")
            return False
        if proc.returncode != 0:
            self.log.append(f"  ! exit {proc.returncode}: {proc.stderr.strip()[:200]}")
            return False
        return True


# ---- steps ----


def _load_permissions(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "manifest" / "permissions.yaml"
    if not path.exists() or yaml is None:
        return {}
    return yaml.safe_load(path.read_text()) or {}


def step_validate(repo_root: Path) -> Manifest:
    """Load manifest, resolve ${VAR}; abort before any write if vars missing."""
    manifest = Manifest.load(repo_root)
    secrets = parse_secrets_env(repo_root / "secrets.env")
    resolved, missing = resolve_manifest_env(manifest, dict(os.environ), secrets)
    if missing:
        raise InstallError(
            "missing required secrets (set them in secrets.env or the environment): "
            + ", ".join(missing)
        )
    return resolved


def step_runtime_dir(home: Path, mut: Mutator) -> None:
    mut.mkdir(home / ".hermes", mode=0o700)


def step_probe_check(tool_root: Path) -> None:
    binary = tool_root / "bin" / "hermes-probe-tcc"
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise InstallError(
            "bin/hermes-probe-tcc missing or not executable. "
            "Run tools/probe-tcc/build.sh and copy build/hermes-probe-tcc to bin/."
        )


def step_claude_version(manifest: Manifest, mut: Mutator) -> None:
    claude = which("claude")
    if not claude:
        mut.log.append("  ! claude CLI not found on PATH — install it, then re-run.")
        return
    try:
        out = subprocess.run([claude, "--version"], capture_output=True, text=True, timeout=10)
        actual = out.stdout.strip().split()[0] if out.stdout.strip() else None
    except (subprocess.SubprocessError, OSError):
        actual = None
    pinned = manifest.claude_version
    if pinned and actual and pinned != actual:
        mut.log.append(f"  ! claude version {actual} != manifest pin {pinned} (not auto-upgrading)")
    else:
        mut.log.append(f"claude version: {actual or 'unknown'}")


def _build_settings(config_root: Path, manifest: Manifest, home: Path) -> dict[str, Any] | None:
    """Merge captured settings.json with MCP servers + opt-in doctor + Layer A hooks.

    The returned dict may still contain ``${HOME}`` tokens; the caller expands
    them to ``home`` when serializing (Decision 20 $HOME templating).
    """
    repo_root = config_root
    settings_path = repo_root / "manifest" / "settings.json"
    settings: dict[str, Any] = {}
    if manifest.has_settings and settings_path.exists():
        settings = json.loads(settings_path.read_text())
    elif not manifest.mcp_servers and not manifest.doctor_on_session_start:
        return None

    # MCP registration → settings.json mcpServers (v1 approach).
    if manifest.mcp_servers:
        settings["mcpServers"] = {
            s.name: {"command": s.command, "args": list(s.args), "env": dict(s.env)}
            for s in manifest.mcp_servers
        }

    # Opt-in SessionStart doctor hook (16.8): never blocks startup.
    if manifest.doctor_on_session_start:
        hooks = settings.setdefault("hooks", {})
        session_start = hooks.setdefault("SessionStart", [])
        cmd = "hermes doctor --check --exit-zero --json > /dev/null"
        already = any(
            any(h.get("command") == cmd for h in entry.get("hooks", []))
            for entry in session_start if isinstance(entry, dict)
        )
        if not already:
            session_start.append({"matcher": "", "hooks": [{"type": "command", "command": cmd}]})

    # Layer A PreToolUse enforcement hook (§14.4): only when permissions.yaml exists.
    perms_path = repo_root / "manifest" / "permissions.yaml"
    if perms_path.exists():
        hooks = settings.setdefault("hooks", {})
        pre = hooks.setdefault("PreToolUse", [])
        cmd = f"{sys.executable} -m hermes.hooks.pretooluse_enforce --permissions {perms_path}"
        already = any(
            any("pretooluse_enforce" in h.get("command", "") for h in entry.get("hooks", []))
            for entry in pre if isinstance(entry, dict)
        )
        if not already:
            pre.append({"matcher": "*", "hooks": [{"type": "command", "command": cmd}]})

    return settings


def step_files(config_root: Path, claude: Path, manifest: Manifest, mut: Mutator, home: Path) -> None:
    mdir = config_root / "manifest"
    if manifest.has_claude_md and (mdir / "CLAUDE.md").exists():
        mut.copy_file(mdir / "CLAUDE.md", claude / "CLAUDE.md", label="~/.claude/CLAUDE.md")
    if manifest.has_keybindings and (mdir / "keybindings.json").exists():
        mut.copy_file(mdir / "keybindings.json", claude / "keybindings.json",
                      label="~/.claude/keybindings.json")
    settings = _build_settings(config_root, manifest, home)
    if settings is not None:
        text = json.dumps(settings, indent=2, sort_keys=True) + "\n"
        text = paths.expand_home(text, home)  # ${HOME} -> target home
        mut.write_text(claude / "settings.json", text, label="~/.claude/settings.json")


def step_skills(repo_root: Path, claude: Path, manifest: Manifest, mut: Mutator) -> None:
    for skill in manifest.skills:
        dst = claude / "skills" / skill.name
        if skill.source == "local":
            files = repo_root / "manifest" / "skills" / skill.name / "files"
            if files.is_dir():
                mut.copytree(files, dst, label=f"skill {skill.name} (local)")
        elif skill.source == "git":
            if dst.exists():
                mut.log.append(f"unchanged: skill {skill.name} (git, already present)")
                continue
            if not skill.repo:
                mut.log.append(f"  ! skill {skill.name}: git source has no repo url, skipping")
                continue
            cmd = ["git", "clone", "--depth", "1"]
            if skill.ref:
                cmd += ["--branch", skill.ref]
            cmd += [skill.repo, str(dst)]
            mut.run(cmd, label=f"skill {skill.name} (git clone)")
        elif skill.source == "marketplace":
            claude_bin = which("claude")
            if not claude_bin:
                mut.log.append(f"  ! skill {skill.name}: claude CLI absent, cannot install marketplace skill")
                continue
            mut.run([claude_bin, "plugin", "install", f"{skill.name}@{skill.marketplace}"],
                    label=f"skill {skill.name} (marketplace)")


def step_plugins(manifest: Manifest, mut: Mutator) -> None:
    if not manifest.plugins:
        return
    claude_bin = which("claude")
    if not claude_bin:
        mut.log.append("  ! claude CLI absent — skipping plugin install ("
                       + ", ".join(p.name for p in manifest.plugins) + ")")
        return
    for plugin in manifest.plugins:
        spec = f"{plugin.name}@{plugin.marketplace}" if plugin.marketplace else plugin.name
        mut.run([claude_bin, "plugin", "install", spec], label=f"plugin {spec}")


def step_commands_hooks(repo_root: Path, claude: Path, manifest: Manifest, mut: Mutator) -> None:
    mdir = repo_root / "manifest"
    cmd_src = mdir / "commands"
    if manifest.commands and cmd_src.is_dir():
        mut.copytree(cmd_src, claude / "commands", label="~/.claude/commands")
    hook_src = mdir / "hooks"
    if manifest.hooks and hook_src.is_dir():
        for name in manifest.hooks:
            f = hook_src / name
            if f.exists():
                mut.copy_file(f, claude / "hooks" / name, label=f"hook {name}")


def step_layer_b(repo_root: Path, home: Path, mut: Mutator) -> None:
    perms = _load_permissions(repo_root)
    lb = (perms.get("security", {}) or {}).get("layer_b", {}) or {}
    profile_path = Path(os.path.expanduser(lb.get("profile_path") or str(home / ".hermes" / "profile.sb")))
    if lb.get("enabled"):
        content = sandbox_profile.generate(perms, sandbox_profile.load_sandbox_rules(),
                                           home=str(home))
        mut.write_text(profile_path, content, mode=0o600, label=f"Layer B profile {profile_path}")
    elif profile_path.exists():
        # 17.9 stale-profile warning — never silently delete.
        mut.log.append(f"  ! stale Layer B profile at {profile_path} (Layer B is disabled); "
                       "leaving it in place — remove manually if unwanted.")


# ---- plugin install orchestration (form B) ----


def _registered_plugins(config_root: Path, manifest: Manifest) -> list:
    has_backups = (config_root / "manifest" / "backups.yaml").exists()
    names = [s.name for s in manifest.mcp_servers]
    return plugins_registry.registered_for_manifest(names, has_backups)


def step_plugin_packages(tool_root: Path, config_root: Path, manifest: Manifest, mut: Mutator) -> None:
    """pipx-inject each registered plugin's package into the hermes venv."""
    plugins = [p for p in _registered_plugins(config_root, manifest)
               if plugins_registry.installable(p)]
    if not plugins:
        return
    pipx = which("pipx")
    for info in plugins:
        if all(which(s) for s in info.console_scripts):
            mut.log.append(f"unchanged: plugin {info.name} (console-script present)")
            continue
        plugin_dir = str(tool_root / info.rel_dir)
        if pipx:
            # --include-apps puts the console-script on PATH (~/.local/bin) so
            # MCP commands resolve and `hermes verify` doesn't see false drift.
            mut.run([pipx, "inject", "hermes", plugin_dir, "--include-apps"],
                    label=f"pipx inject {info.name}")
        else:
            mut.run([sys.executable, "-m", "pip", "install", plugin_dir],
                    label=f"pip install {info.name}")


def step_launchd_jobs(tool_root: Path, config_root: Path, home: Path, manifest: Manifest, mut: Mutator) -> None:
    """Write + load a LaunchAgent for each registered plugin that declares one."""
    jobs = [p for p in _registered_plugins(config_root, manifest) if p.launchd]
    if not jobs:
        return
    secrets = parse_secrets_env(config_root / "secrets.env")
    agents = tool_launchd.launch_agents_dir(home)
    launchctl = which("launchctl") or "/bin/launchctl"
    for info in jobs:
        job = info.launchd
        program_args = [sys.executable, "-m", job.module, *job.args]
        # launchd jobs don't inherit the login shell, so embed the secrets the
        # job needs plus the config root (so the CLI finds manifest/backups.yaml).
        env = {k: secrets[k] for k in job.env_keys if k in secrets}
        env["HERMES_MANIFEST_DIR"] = str(config_root)
        # launchd's default PATH omits Homebrew, so jobs that shell out to
        # restic/ffmpeg/etc. can't find them; prepend the usual brew prefixes.
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        plist = tool_launchd.generate_agent_plist(
            job.label, program_args, keep_alive=job.keep_alive,
            start_interval=job.start_interval, env=env)
        plist_path = agents / f"{job.label}.plist"
        mut.write_text(plist_path, plist, mode=0o600,
                       label=f"~/Library/LaunchAgents/{job.label}.plist")
        mut.run([launchctl, "load", "-w", str(plist_path)], label=f"launchctl load {job.label}")


# ---- orchestrator ----


@dataclass
class InstallResult:
    actions: list[str]


def install(config_root: str | Path | None = None, home: str | Path | None = None,
            *, tool_root: str | Path | None = None, dry_run: bool = False) -> InstallResult:
    cfg = Path(config_root) if config_root else paths.config_root()
    tool = Path(tool_root) if tool_root else paths.tool_root()
    home_path = Path(home).expanduser() if home else Path.home()
    claude = home_path / ".claude"

    # Fail-fast precondition checks BEFORE any mutation.
    manifest = step_validate(cfg)
    step_probe_check(tool)

    mut = Mutator(dry_run=dry_run)
    step_runtime_dir(home_path, mut)
    step_claude_version(manifest, mut)
    step_files(cfg, claude, manifest, mut, home_path)
    step_skills(cfg, claude, manifest, mut)
    step_plugins(manifest, mut)
    step_commands_hooks(cfg, claude, manifest, mut)
    step_layer_b(cfg, home_path, mut)
    step_plugin_packages(tool, cfg, manifest, mut)
    step_launchd_jobs(tool, cfg, home_path, manifest, mut)

    return InstallResult(actions=mut.log)
