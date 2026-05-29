"""Registry of bundled plugins — the single source install/verify consult to
know what to inject and which launchd jobs to load (design Decision: plugin
install orchestration, form B).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LaunchdJob:
    label: str
    # ProgramArguments are built at install time; `module` runs `python -m <module> <args>`.
    module: str
    args: tuple[str, ...] = ()
    keep_alive: bool = False           # True → long-running worker; False → periodic
    start_interval: int | None = None  # seconds, for periodic jobs
    # Secret env-var names to embed in the plist (launchd doesn't inherit the
    # login shell). Only keys actually present in secrets.env are injected.
    env_keys: tuple[str, ...] = ()


@dataclass(frozen=True)
class PluginInfo:
    name: str                 # matches the MCP server name where applicable
    rel_dir: str              # path relative to tool_root
    kind: str                 # "mcp" | "skill" | "cli"
    console_scripts: tuple[str, ...] = ()
    launchd: LaunchdJob | None = None
    # Brew-installable binaries the plugin shells out to (fail-soft at runtime
    # per Decision 18; install surfaces them up front via `brew install <pkg>`).
    brew_deps: tuple[str, ...] = ()


REGISTRY: dict[str, PluginInfo] = {
    "vision": PluginInfo(
        name="vision", rel_dir="manifest/skills/vision", kind="skill"),
    "macos-control": PluginInfo(
        name="macos-control", rel_dir="plugins/macos_control", kind="mcp",
        console_scripts=("hermes-macos-control",)),
    "telegram-bot": PluginInfo(
        name="telegram-bot", rel_dir="plugins/telegram_bot", kind="mcp",
        console_scripts=("hermes-telegram-bot",),
        launchd=LaunchdJob(label="com.hermes.telegram-bot",
                           module="telegram_bot.worker", keep_alive=True,
                           env_keys=("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_CHAT_IDS"))),
    "voice": PluginInfo(
        name="voice", rel_dir="plugins/voice", kind="mcp",
        console_scripts=("hermes-voice",),
        brew_deps=("whisper-cpp", "ffmpeg")),
    "backups": PluginInfo(
        name="backups", rel_dir="plugins/backups", kind="cli",
        console_scripts=("hermes-backup",),
        brew_deps=("restic",),
        launchd=LaunchdJob(label="com.hermes.backup",
                           module="backups.cli", args=("backup",),
                           keep_alive=False, start_interval=3600,
                           env_keys=("RESTIC_PASSWORD", "RESTIC_REPOSITORY",
                                     "BACKUP_EXTRA_EXCLUDES", "BACKUP_ALERT_CHAT_ID",
                                     "TELEGRAM_BOT_TOKEN", "AWS_ACCESS_KEY_ID",
                                     "AWS_SECRET_ACCESS_KEY", "B2_ACCOUNT_ID",
                                     "B2_ACCOUNT_KEY"))),
}


def get(name: str) -> PluginInfo | None:
    return REGISTRY.get(name)


def registered_for_manifest(mcp_server_names: list[str], has_backups: bool) -> list[PluginInfo]:
    """Plugins the manifest actually pulls in: MCP servers present in the
    registry, plus `backups` if a backups.yaml exists. Skills are handled by
    the skill install path, not here."""
    out: list[PluginInfo] = []
    seen: set[str] = set()
    for name in mcp_server_names:
        info = REGISTRY.get(name)
        if info and info.kind != "skill" and info.name not in seen:
            out.append(info)
            seen.add(info.name)
    if has_backups and "backups" not in seen:
        out.append(REGISTRY["backups"])
        seen.add("backups")
    return out


def installable(info: PluginInfo) -> bool:
    """True if this plugin is a pip-installable package (not a bare skill)."""
    return info.kind in ("mcp", "cli") and bool(info.console_scripts)
