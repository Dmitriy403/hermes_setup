"""`hermes verify` — diff a running machine against the manifest.

Classifies each component as match / missing / extra / modified. Does NOT
inspect TCC state (that is `hermes doctor`'s job) — verify covers files,
skills, plugins, MCP servers, the probe binary, and the Layer B profile.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import paths
from .install.installer import _build_settings
from .manifest import Manifest, parse_secrets_env, resolve_manifest_env

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

# settings.json keys that are user-local / machine-specific and excluded
# from the structural diff.
_USER_LOCAL_SETTINGS_KEYS: frozenset[str] = frozenset()


@dataclass
class DriftRecord:
    component: str
    name: str
    status: str  # match | missing | extra | modified
    detail: str | None = None


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dir_digest(root: Path) -> dict[str, str]:
    """Map relative path -> sha256 for every file under root."""
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    for f in sorted(root.rglob("*")):
        if f.is_file():
            out[str(f.relative_to(root))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


# ---- per-component verifiers ----


def _verify_verbatim(component: str, manifest_file: Path, target: Path, present: bool) -> list[DriftRecord]:
    if not present:
        return []
    if not manifest_file.exists():
        return [DriftRecord(component, component, "missing", "not in manifest tree")]
    if not target.exists():
        return [DriftRecord(component, component, "missing", f"absent at {target}")]
    if _sha256(manifest_file) == _sha256(target):
        return [DriftRecord(component, component, "match")]
    return [DriftRecord(component, component, "modified", "content differs")]


def _verify_settings(config_root: Path, claude: Path, manifest: Manifest, home: Path) -> list[DriftRecord]:
    expected = _build_settings(config_root, manifest, home)
    if expected is None:
        return []
    target = claude / "settings.json"
    if not target.exists():
        return [DriftRecord("settings", "settings.json", "missing", f"absent at {target}")]
    actual = json.loads(target.read_text())

    def strip(d: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in d.items() if k not in _USER_LOCAL_SETTINGS_KEYS}

    # Expected may carry ${HOME}; expand to match what install wrote.
    exp_s = paths.expand_home(json.dumps(strip(expected), sort_keys=True), home)
    act_s = json.dumps(strip(actual), sort_keys=True)
    if exp_s == act_s:
        return [DriftRecord("settings", "settings.json", "match")]
    return [DriftRecord("settings", "settings.json", "modified", "structural diff")]


def _verify_skills(repo_root: Path, claude: Path, manifest: Manifest) -> list[DriftRecord]:
    records: list[DriftRecord] = []
    manifest_names = {s.name for s in manifest.skills}
    for skill in manifest.skills:
        dst = claude / "skills" / skill.name
        if skill.source == "local":
            files = repo_root / "manifest" / "skills" / skill.name / "files"
            if not dst.is_dir():
                records.append(DriftRecord("skill", skill.name, "missing", "not installed"))
            elif _dir_digest(files) == _dir_digest(dst):
                records.append(DriftRecord("skill", skill.name, "match"))
            else:
                records.append(DriftRecord("skill", skill.name, "modified", "file contents differ"))
        elif skill.source == "git":
            if not dst.is_dir():
                records.append(DriftRecord("skill", skill.name, "missing", "not cloned"))
            else:
                head = _git_head(dst)
                if skill.ref and head and not head.startswith(skill.ref) and head != skill.ref:
                    records.append(DriftRecord("skill", skill.name, "modified",
                                               f"HEAD {head[:12]} != ref {skill.ref}"))
                else:
                    records.append(DriftRecord("skill", skill.name, "match"))
        else:  # marketplace
            records.append(DriftRecord("skill", skill.name,
                                       "match" if dst.exists() else "missing"))

    # extra skills on machine not in manifest
    skills_dir = claude / "skills"
    if skills_dir.is_dir():
        for entry in sorted(skills_dir.iterdir()):
            if entry.is_dir() and entry.name not in manifest_names and not entry.name.startswith("."):
                records.append(DriftRecord("skill", entry.name, "extra", "on machine, not in manifest"))
    return records


def _git_head(d: Path) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(d), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else None
    except (FileNotFoundError, subprocess.SubprocessError):
        return None


def _verify_plugins(claude: Path, manifest: Manifest) -> list[DriftRecord]:
    installed_path = claude / "plugins" / "installed_plugins.json"
    installed: dict[str, str] = {}
    if installed_path.exists():
        data = json.loads(installed_path.read_text())
        for full, entries in (data.get("plugins", {}) or {}).items():
            name = full.split("@", 1)[0]
            ver = entries[0].get("version") if isinstance(entries, list) and entries else None
            installed[name] = ver
    records: list[DriftRecord] = []
    for plugin in manifest.plugins:
        if plugin.name not in installed:
            records.append(DriftRecord("plugin", plugin.name, "missing", "not installed"))
        elif plugin.version and installed[plugin.name] and plugin.version != installed[plugin.name]:
            records.append(DriftRecord("plugin", plugin.name, "modified",
                                       f"installed {installed[plugin.name]} != manifest {plugin.version}"))
        else:
            records.append(DriftRecord("plugin", plugin.name, "match"))
    return records


def _verify_probe(tool_root: Path) -> list[DriftRecord]:
    sidecar = tool_root / "manifest" / "probe-tcc.yaml"
    binary = tool_root / "bin" / "hermes-probe-tcc"
    if not sidecar.exists() or yaml is None:
        return []
    meta = (yaml.safe_load(sidecar.read_text()) or {}).get("probe", {})
    expected = meta.get("expected_cdhash")
    if not binary.is_file():
        return [DriftRecord("probe-tcc", "hermes-probe-tcc", "missing", "binary absent")]
    actual = _probe_cdhash(binary)
    if expected and actual and expected != actual:
        return [DriftRecord("probe-tcc", "hermes-probe-tcc", "modified",
                            f"cdhash {actual} != expected {expected}")]
    return [DriftRecord("probe-tcc", "hermes-probe-tcc", "match")]


def _probe_cdhash(binary: Path) -> str | None:
    try:
        out = subprocess.run(["codesign", "--display", "--verbose=4", str(binary)],
                             capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    for line in (out.stdout + out.stderr).splitlines():
        line = line.strip()
        if line.startswith("CDHash="):
            return line[len("CDHash="):]
    return None


def _verify_layer_b(repo_root: Path, home: Path) -> list[DriftRecord]:
    perms_path = repo_root / "manifest" / "permissions.yaml"
    if not perms_path.exists() or yaml is None:
        return []
    perms = yaml.safe_load(perms_path.read_text()) or {}
    lb = (perms.get("security", {}) or {}).get("layer_b", {}) or {}
    profile = Path(os.path.expanduser(lb.get("profile_path") or str(home / ".hermes" / "profile.sb")))
    if not lb.get("enabled") and profile.exists():
        return [DriftRecord("layer-b", "profile.sb", "extra",
                            f"stale profile at {profile} (Layer B disabled)")]
    return []


# ---- orchestrator ----


def verify(config_root: str | Path | None = None, home: str | Path | None = None,
           *, tool_root: str | Path | None = None) -> list[DriftRecord]:
    cfg = Path(config_root) if config_root else paths.config_root()
    tool = Path(tool_root) if tool_root else paths.tool_root()
    home_path = Path(home).expanduser() if home else Path.home()
    claude = home_path / ".claude"

    manifest = Manifest.load(cfg)
    # Resolve for settings comparison (best-effort; unresolved vars stay as ${VAR}).
    secrets = parse_secrets_env(cfg / "secrets.env")
    resolved, _ = resolve_manifest_env(manifest, dict(os.environ), secrets)

    mdir = cfg / "manifest"
    records: list[DriftRecord] = []
    records += _verify_verbatim("claude_md", mdir / "CLAUDE.md", claude / "CLAUDE.md", manifest.has_claude_md)
    records += _verify_verbatim("keybindings", mdir / "keybindings.json",
                                claude / "keybindings.json", manifest.has_keybindings)
    records += _verify_settings(cfg, claude, resolved, home_path)
    records += _verify_skills(cfg, claude, manifest)
    records += _verify_plugins(claude, manifest)
    records += _verify_probe(tool)
    records += _verify_layer_b(cfg, home_path)
    return records


def has_drift(records: list[DriftRecord]) -> bool:
    return any(r.status != "match" for r in records)


def render_human(records: list[DriftRecord]) -> str:
    if not records:
        return "no components to verify"
    lines = ["Hermes verify", ""]
    width = max(len(r.name) for r in records) + 2
    for r in sorted(records, key=lambda r: (r.component, r.name)):
        tag = r.name.ljust(width)
        line = f"  [{r.status:8}] {r.component}: {tag}"
        if r.detail:
            line += f" — {r.detail}"
        lines.append(line)
    drift = [r for r in records if r.status != "match"]
    lines.append("")
    lines.append("no drift" if not drift else f"{len(drift)} drifted component(s)")
    return "\n".join(lines)


def render_json(records: list[DriftRecord]) -> str:
    return json.dumps({"drift": [asdict(r) for r in records]}, indent=2, sort_keys=True)
