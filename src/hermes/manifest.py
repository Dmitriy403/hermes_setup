"""Manifest schema (schema_version 1) and lossless load/save.

Layout (Decision 2 in design.md):

    manifest/
      hermes.yaml          root index + version pins + inline lists
      CLAUDE.md            verbatim (presence flagged in root)
      settings.json        redacted copy (presence flagged)
      keybindings.json     verbatim, optional
      plugins.yaml         list of {name, marketplace, version}
      skills/<name>/skill.yaml
      mcp/<name>.yaml      command/args/env (env values may be ${VAR})
      commands/            verbatim command files
      hooks/               hook scripts referenced from settings.json

Load → save → load is a fixed point: lists are sorted by name and YAML is
dumped deterministically so re-capture produces minimal diffs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

SCHEMA_VERSION = 1
_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ManifestError(Exception):
    """Raised for malformed manifests."""


# ---- component dataclasses ----


@dataclass
class SkillEntry:
    name: str
    source: str  # "local" | "git" | "marketplace"
    repo: str | None = None
    ref: str | None = None
    marketplace: str | None = None
    version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "source": self.source}
        for key in ("repo", "ref", "marketplace", "version"):
            val = getattr(self, key)
            if val is not None:
                d[key] = val
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SkillEntry":
        if "name" not in d or "source" not in d:
            raise ManifestError(f"skill entry missing name/source: {d!r}")
        return cls(
            name=d["name"], source=d["source"], repo=d.get("repo"),
            ref=d.get("ref"), marketplace=d.get("marketplace"), version=d.get("version"),
        )


@dataclass
class PluginEntry:
    name: str
    marketplace: str | None = None
    version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name}
        if self.marketplace is not None:
            d["marketplace"] = self.marketplace
        if self.version is not None:
            d["version"] = self.version
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PluginEntry":
        if "name" not in d:
            raise ManifestError(f"plugin entry missing name: {d!r}")
        return cls(name=d["name"], marketplace=d.get("marketplace"), version=d.get("version"))


@dataclass
class McpServer:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "command": self.command,
                "args": list(self.args), "env": dict(self.env)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "McpServer":
        if "name" not in d or "command" not in d:
            raise ManifestError(f"mcp server missing name/command: {d!r}")
        return cls(name=d["name"], command=d["command"],
                   args=list(d.get("args", [])), env=dict(d.get("env", {})))


@dataclass
class Manifest:
    schema_version: int = SCHEMA_VERSION
    claude_version: str | None = None
    skills: list[SkillEntry] = field(default_factory=list)
    plugins: list[PluginEntry] = field(default_factory=list)
    mcp_servers: list[McpServer] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    hooks: list[str] = field(default_factory=list)
    has_claude_md: bool = False
    has_settings: bool = False
    has_keybindings: bool = False
    doctor_on_session_start: bool = False

    # ---- load ----

    @classmethod
    def load(cls, repo_root: str | Path) -> "Manifest":
        if yaml is None:
            raise ManifestError("pyyaml is required to load a manifest")
        root = Path(repo_root)
        mdir = root / "manifest"
        hermes_yaml = mdir / "hermes.yaml"
        if not hermes_yaml.exists():
            raise ManifestError(f"no manifest at {hermes_yaml}")

        try:
            raw = yaml.safe_load(hermes_yaml.read_text()) or {}
        except yaml.YAMLError as exc:
            raise ManifestError(f"hermes.yaml is not valid YAML: {exc}") from exc
        if not isinstance(raw, dict):
            raise ManifestError("hermes.yaml top level must be a mapping")

        sv = raw.get("schema_version")
        if sv != SCHEMA_VERSION:
            raise ManifestError(f"unsupported schema_version: {sv!r} (expected {SCHEMA_VERSION})")

        m = cls(schema_version=SCHEMA_VERSION, claude_version=raw.get("claude_version"))

        for s in raw.get("skills", []) or []:
            m.skills.append(SkillEntry.from_dict(s))

        # plugins: prefer plugins.yaml sidecar, else inline.
        plugins_yaml = mdir / "plugins.yaml"
        if plugins_yaml.exists():
            pdata = yaml.safe_load(plugins_yaml.read_text()) or []
            for p in pdata:
                m.plugins.append(PluginEntry.from_dict(p))
        else:
            for p in raw.get("plugins", []) or []:
                m.plugins.append(PluginEntry.from_dict(p))

        # mcp servers: each referenced by name → manifest/mcp/<name>.yaml.
        for name in raw.get("mcp_servers", []) or []:
            sidecar = mdir / "mcp" / f"{name}.yaml"
            if not sidecar.exists():
                raise ManifestError(f"mcp server '{name}' referenced but {sidecar} missing")
            sd = yaml.safe_load(sidecar.read_text()) or {}
            sd.setdefault("name", name)
            m.mcp_servers.append(McpServer.from_dict(sd))

        m.commands = list(raw.get("commands", []) or [])
        m.hooks = list(raw.get("hooks", []) or [])
        files = raw.get("files", {}) or {}
        m.has_claude_md = bool(files.get("claude_md", False))
        m.has_settings = bool(files.get("settings", False))
        m.has_keybindings = bool(files.get("keybindings", False))
        hooks_cfg = raw.get("hooks_config", {}) or {}
        m.doctor_on_session_start = bool(hooks_cfg.get("doctor_on_session_start", False))
        return m

    # ---- save ----

    def save(self, repo_root: str | Path) -> None:
        if yaml is None:
            raise ManifestError("pyyaml is required to save a manifest")
        root = Path(repo_root)
        mdir = root / "manifest"
        mdir.mkdir(parents=True, exist_ok=True)

        skills_sorted = sorted(self.skills, key=lambda s: s.name)
        plugins_sorted = sorted(self.plugins, key=lambda p: p.name)
        mcp_sorted = sorted(self.mcp_servers, key=lambda s: s.name)

        root_doc: dict[str, Any] = {
            "schema_version": self.schema_version,
        }
        if self.claude_version is not None:
            root_doc["claude_version"] = self.claude_version
        root_doc["skills"] = [s.to_dict() for s in skills_sorted]
        root_doc["mcp_servers"] = [s.name for s in mcp_sorted]
        root_doc["commands"] = sorted(self.commands)
        root_doc["hooks"] = sorted(self.hooks)
        root_doc["files"] = {
            "claude_md": self.has_claude_md,
            "settings": self.has_settings,
            "keybindings": self.has_keybindings,
        }
        if self.doctor_on_session_start:
            root_doc["hooks_config"] = {"doctor_on_session_start": True}

        (mdir / "hermes.yaml").write_text(_dump(root_doc))

        # plugins sidecar.
        (mdir / "plugins.yaml").write_text(_dump([p.to_dict() for p in plugins_sorted]))

        # mcp sidecars.
        mcp_dir = mdir / "mcp"
        mcp_dir.mkdir(parents=True, exist_ok=True)
        for server in mcp_sorted:
            (mcp_dir / f"{server.name}.yaml").write_text(_dump(server.to_dict()))


def _dump(obj: Any) -> str:
    return yaml.safe_dump(obj, sort_keys=True, default_flow_style=False, allow_unicode=True)


# ---- env-var resolution (§2.4) ----


def parse_secrets_env(path: str | Path) -> dict[str, str]:
    """Parse a KEY=VALUE secrets.env file. Ignores blanks and # comments."""
    out: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            out[key] = value
    return out


# ${HOME} is path templating (Decision 20), not a secret — install expands it
# to the target home. It is never resolved here nor reported as missing.
_PATH_TOKENS = frozenset({"HOME"})


def resolve_string(value: str, sources: dict[str, str]) -> tuple[str, list[str]]:
    """Replace ${VAR} placeholders in a string. Returns (resolved, missing)."""
    missing: list[str] = []

    def repl(match: re.Match[str]) -> str:
        var = match.group(1)
        if var in _PATH_TOKENS:
            return match.group(0)  # leave ${HOME} for install-time path expansion
        if var in sources:
            return sources[var]
        missing.append(var)
        return match.group(0)

    return _ENV_RE.sub(repl, value), missing


def resolve_manifest_env(
    manifest: Manifest, environ: dict[str, str], secrets: dict[str, str] | None = None
) -> tuple[Manifest, list[str]]:
    """Return a copy of the manifest with MCP env ${VAR} placeholders resolved.

    Resolution precedence: os.environ first, then secrets.env. Reports every
    missing variable (deduplicated, in first-seen order).
    """
    sources: dict[str, str] = {}
    if secrets:
        sources.update(secrets)
    sources.update(environ)  # environ wins over secrets.env

    missing: list[str] = []
    seen: set[str] = set()
    new_servers: list[McpServer] = []
    for server in manifest.mcp_servers:
        new_env: dict[str, str] = {}
        for k, v in server.env.items():
            resolved, miss = resolve_string(v, sources)
            for var in miss:
                if var not in seen:
                    seen.add(var)
                    missing.append(var)
            new_env[k] = resolved
        new_servers.append(McpServer(name=server.name, command=server.command,
                                     args=list(server.args), env=new_env))

    resolved_manifest = Manifest(
        schema_version=manifest.schema_version,
        claude_version=manifest.claude_version,
        skills=list(manifest.skills),
        plugins=list(manifest.plugins),
        mcp_servers=new_servers,
        commands=list(manifest.commands),
        hooks=list(manifest.hooks),
        has_claude_md=manifest.has_claude_md,
        has_settings=manifest.has_settings,
        has_keybindings=manifest.has_keybindings,
        doctor_on_session_start=manifest.doctor_on_session_start,
    )
    return resolved_manifest, missing
