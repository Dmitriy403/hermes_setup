"""Tests for §5 — plugin install orchestration (form B).

Registry mapping, pipx-inject + launchd argv (via dry-run install), launchd
plist content, and verify drift for a missing console-script / launchd plist.
The real pipx inject / launchctl load are the live edge (dry-run here).

    PYTHONPATH=src python3 tests/test_plugin_orchestration.py
"""

from __future__ import annotations

import contextlib
import os
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hermes import plugins_registry as reg  # noqa: E402
from hermes.install import launchd as tl  # noqa: E402
from hermes.install.installer import (  # noqa: E402
    Mutator, install, step_launchd_jobs, step_plugin_brew_deps,
)
from hermes.manifest import Manifest, McpServer  # noqa: E402
from hermes.verify import verify  # noqa: E402

_TG = "123456789:AAEdefGhIjKlMnOpQrStUvWxYz012345678"


# ---- 5.1 registry ----

def test_registry_maps_known_plugins():
    assert reg.get("telegram-bot").rel_dir == "plugins/telegram_bot"
    assert reg.get("telegram-bot").launchd.label == "com.hermes.telegram-bot"
    assert reg.get("backups").launchd.start_interval == 3600
    assert reg.get("vision").kind == "skill"
    assert reg.installable(reg.get("macos-control")) is True
    assert reg.installable(reg.get("vision")) is False


def test_registered_for_manifest():
    plugins = reg.registered_for_manifest(["telegram-bot", "unknown-server"], has_backups=True)
    names = {p.name for p in plugins}
    assert names == {"telegram-bot", "backups"}   # unknown skipped, backups added
    # no backups.yaml → no backups
    assert {p.name for p in reg.registered_for_manifest(["voice"], has_backups=False)} == {"voice"}


# ---- launchd plist content ----

def test_agent_plist_keepalive_vs_interval():
    ka = tl.generate_agent_plist("com.x", ["/py", "-m", "w"], keep_alive=True)
    assert "KeepAlive" in ka and "RunAtLoad" in ka
    iv = tl.generate_agent_plist("com.y", ["/py", "-m", "b", "backup"], start_interval=3600)
    assert "StartInterval" in iv and "3600" in iv


def test_agent_plist_injects_env():
    p = tl.generate_agent_plist("com.z", ["/py"], env={"RESTIC_PASSWORD": "s3cr3t"})
    assert "EnvironmentVariables" in p and "RESTIC_PASSWORD" in p and "s3cr3t" in p
    # no env → no EnvironmentVariables block
    assert "EnvironmentVariables" not in tl.generate_agent_plist("com.z", ["/py"])


def test_registry_declares_secret_env_keys():
    assert "RESTIC_PASSWORD" in reg.get("backups").launchd.env_keys
    assert "TELEGRAM_BOT_TOKEN" in reg.get("telegram-bot").launchd.env_keys


# ---- 5.3 step_launchd_jobs embeds secrets into the plist ----

def _fake_launchctl_on_path(d: Path) -> None:
    """Put a no-op `launchctl` first on PATH so the real one never runs."""
    binp = d / "fakebin"
    binp.mkdir(exist_ok=True)
    lc = binp / "launchctl"
    lc.write_text("#!/bin/sh\nexit 0\n")
    lc.chmod(lc.stat().st_mode | stat.S_IXUSR)
    os.environ["PATH"] = f"{binp}{os.pathsep}{os.environ['PATH']}"


def test_launchd_job_embeds_secret_and_config_dir():
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        repo, home = dd / "repo", dd / "home"
        repo.mkdir(); home.mkdir()
        # backups.yaml present → backups job is registered; secrets.env holds the key
        (repo / "manifest").mkdir(parents=True)
        (repo / "manifest" / "backups.yaml").write_text(
            "schema_version: 1\nsources: [\"~/x\"]\ndestination: {kind: local, path: ~/backups}\n")
        (repo / "secrets.env").write_text("RESTIC_PASSWORD=top-secret-pw\n")
        prev_path = os.environ["PATH"]
        _fake_launchctl_on_path(dd)
        try:
            mut = Mutator(dry_run=False)
            step_launchd_jobs(repo, repo, home, Manifest(mcp_servers=[]), mut)
        finally:
            os.environ["PATH"] = prev_path
        plist = (home / "Library" / "LaunchAgents" / "com.hermes.backup.plist").read_text()
        assert "RESTIC_PASSWORD" in plist and "top-secret-pw" in plist
        assert "HERMES_MANIFEST_DIR" in plist and str(repo) in plist
        assert "/opt/homebrew/bin" in plist  # PATH so the job finds restic
        # plist holds a secret → must be 0600
        mode = (home / "Library" / "LaunchAgents" / "com.hermes.backup.plist").stat().st_mode
        assert stat.S_IMODE(mode) == 0o600


# ---- 5.2/5.3 install wires inject + launchd (dry-run) ----

def _repo_with_telegram(repo: Path) -> None:
    m = Manifest(mcp_servers=[McpServer(
        "telegram-bot", "hermes-telegram-bot", [],
        {"TELEGRAM_BOT_TOKEN": "${TELEGRAM_BOT_TOKEN}",
         "TELEGRAM_ALLOWED_CHAT_IDS": "${TELEGRAM_ALLOWED_CHAT_IDS}"})])
    m.save(repo)
    (repo / "bin").mkdir(parents=True, exist_ok=True)
    probe = repo / "bin" / "hermes-probe-tcc"
    probe.write_text("#!/bin/sh\n")
    probe.chmod(probe.stat().st_mode | stat.S_IXUSR)
    (repo / "manifest" / "permissions.yaml").write_text("schema_version: 1\n")
    (repo / "secrets.env").write_text(
        f"TELEGRAM_BOT_TOKEN={_TG}\nTELEGRAM_ALLOWED_CHAT_IDS=1\n")


@contextlib.contextmanager
def _empty_path(d: Path):
    """Isolate PATH to an empty dir so which() can't see real hermes-* scripts
    or pipx installed on the dev machine — keeps these tests hermetic."""
    binp = d / "emptybin"; binp.mkdir(exist_ok=True)
    prev = os.environ["PATH"]
    os.environ["PATH"] = str(binp)
    try:
        yield
    finally:
        os.environ["PATH"] = prev


def test_install_dry_run_injects_and_loads():
    with tempfile.TemporaryDirectory() as d:
        repo, tgt = Path(d) / "repo", Path(d) / "tgt"
        repo.mkdir(); tgt.mkdir()
        _repo_with_telegram(repo)
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_ALLOWED_CHAT_IDS", None)
        with _empty_path(Path(d)):  # console-script absent → install must inject
            res = install(config_root=repo, home=tgt, tool_root=repo, dry_run=True)
        log = "\n".join(res.actions)
        # plugin package injected (pipx present on dev machine → inject; else pip)
        assert ("pipx inject telegram-bot" in log) or ("pip install telegram-bot" in log), log
        # launchd plist written + loaded
        assert "com.hermes.telegram-bot.plist" in log
        assert "launchctl load com.hermes.telegram-bot" in log
        # dry-run wrote nothing
        assert not (tgt / "Library" / "LaunchAgents").exists()


# ---- 5.5 verify drift ----

def test_verify_flags_missing_package_and_launchd():
    with tempfile.TemporaryDirectory() as d:
        repo, tgt = Path(d) / "repo", Path(d) / "tgt"
        repo.mkdir(); tgt.mkdir()
        _repo_with_telegram(repo)
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_ALLOWED_CHAT_IDS", None)
        with _empty_path(Path(d)):  # ensure hermes-telegram-bot isn't found on PATH
            records = verify(config_root=repo, home=tgt, tool_root=repo)
        pkg = next(r for r in records if r.component == "plugin-package" and r.name == "telegram-bot")
        assert pkg.status == "missing"          # hermes-telegram-bot not on PATH
        ld = next(r for r in records if r.component == "launchd" and r.name == "com.hermes.telegram-bot")
        assert ld.status == "missing"           # no plist installed


# ---- 18.6/18.7 factory install + brew_deps surfacing ----

def _factory_repo(repo: Path, mcp_servers: tuple[str, ...]) -> None:
    """Write a minimal factory-shaped manifest under `repo` registering the
    given MCP servers (sidecars copied from the real tool manifest/mcp/)."""
    (repo / "manifest" / "mcp").mkdir(parents=True)
    real_mcp = Path(__file__).resolve().parents[1] / "manifest" / "mcp"
    body = ("schema_version: 1\nskills: []\n"
            f"mcp_servers:\n" + "".join(f"- {n}\n" for n in mcp_servers) +
            "commands: []\nhooks: []\n"
            "files:\n  claude_md: false\n  settings: false\n  keybindings: false\n")
    (repo / "manifest" / "hermes.yaml").write_text(body)
    for name in mcp_servers:
        (repo / "manifest" / "mcp" / f"{name}.yaml").write_text(
            (real_mcp / f"{name}.yaml").read_text())
    (repo / "bin").mkdir(parents=True, exist_ok=True)
    probe = repo / "bin" / "hermes-probe-tcc"
    probe.write_text("#!/bin/sh\n")
    probe.chmod(probe.stat().st_mode | stat.S_IXUSR)
    (repo / "manifest" / "permissions.yaml").write_text("schema_version: 1\n")


def test_factory_install_dry_run_registers_no_secret_plugins():
    """Bare install (tool_root == config_root, factory manifest) injects
    macos-control + voice; never touches telegram-bot/backups."""
    with tempfile.TemporaryDirectory() as d:
        repo, tgt = Path(d) / "repo", Path(d) / "tgt"
        repo.mkdir(); tgt.mkdir()
        _factory_repo(repo, ("macos-control", "voice"))
        with _empty_path(Path(d)):
            res = install(config_root=repo, home=tgt, tool_root=repo, dry_run=True)
        log = "\n".join(res.actions)
        for name in ("macos-control", "voice"):
            assert (f"pipx inject {name}" in log) or (f"pip install {name}" in log), log
        # opt-in plugins must NOT appear
        assert "telegram-bot" not in log
        assert "com.hermes.telegram-bot" not in log
        assert "com.hermes.backup" not in log


def test_step_plugin_brew_deps_warns_for_missing_voice_deps():
    """voice → `brew install whisper-cpp ffmpeg` warning when bins absent."""
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d) / "repo"; repo.mkdir()
        _factory_repo(repo, ("voice",))
        m = Manifest.load(repo)
        with _empty_path(Path(d)):
            mut = Mutator(dry_run=True)
            step_plugin_brew_deps(repo, m, mut)
    assert any("voice pre-reqs missing" in line and "whisper-cpp" in line and "ffmpeg" in line
               for line in mut.log), mut.log


def test_verify_emits_brew_deps_drift_for_voice():
    with tempfile.TemporaryDirectory() as d:
        repo, tgt = Path(d) / "repo", Path(d) / "tgt"
        repo.mkdir(); tgt.mkdir()
        _factory_repo(repo, ("voice",))
        with _empty_path(Path(d)):
            records = verify(config_root=repo, home=tgt, tool_root=repo)
    bd = [r for r in records if r.component == "brew-deps" and r.name == "voice"]
    assert bd, [r.component for r in records]
    assert bd[0].status == "missing" and "whisper-cpp" in (bd[0].detail or "")


# ---- 18.11 factory must NOT opt into backups from a .example starter ----

def test_factory_does_not_register_backups_when_only_example_present():
    """Renaming the public starter to `manifest/backups.yaml.example` removes
    the false opt-in: `_registered_plugins` only treats a REAL backups.yaml
    as an opt-in signal."""
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d) / "repo"; repo.mkdir()
        _factory_repo(repo, ("macos-control", "voice"))
        # .example present but no real backups.yaml — must NOT trigger opt-in.
        (repo / "manifest" / "backups.yaml.example").write_text("# starter\n")
        m = Manifest.load(repo)
        from hermes.install.installer import _registered_plugins
        names = {p.name for p in _registered_plugins(repo, m)}
    assert "backups" not in names, names
    assert names == {"macos-control", "voice"}


# ---- 18.12 brew_deps formula:binary split ----

def test_parse_brew_dep_formula_only_and_with_binary():
    assert reg.parse_brew_dep("ffmpeg") == ("ffmpeg", "ffmpeg")
    assert reg.parse_brew_dep("whisper-cpp:whisper-cli") == ("whisper-cpp", "whisper-cli")


def test_brew_deps_check_uses_binary_warning_uses_formula():
    """When the formula and binary differ, drift must clear once the BINARY
    exists, and the warning must point the user at the FORMULA."""
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        repo = dd / "repo"; repo.mkdir()
        _factory_repo(repo, ("voice",))
        # Provide stubs for the *binaries* voice probes: whisper-cli + ffmpeg.
        binp = dd / "fakebin"; binp.mkdir()
        for name in ("whisper-cli", "ffmpeg"):
            stub = binp / name
            stub.write_text("#!/bin/sh\nexit 0\n")
            stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
        prev = os.environ["PATH"]
        os.environ["PATH"] = f"{binp}{os.pathsep}{prev}"
        try:
            records = verify(config_root=repo, home=dd / "home", tool_root=repo)
        finally:
            os.environ["PATH"] = prev
    bd = next(r for r in records if r.component == "brew-deps" and r.name == "voice")
    assert bd.status == "match", bd

    # Same setup but NO binaries on PATH — must say `brew install whisper-cpp`
    # (the FORMULA name), not `brew install whisper-cli` (the binary).
    with tempfile.TemporaryDirectory() as d:
        repo = Path(d) / "repo"; repo.mkdir()
        _factory_repo(repo, ("voice",))
        with _empty_path(Path(d)):
            records = verify(config_root=repo, home=Path(d) / "home", tool_root=repo)
    bd = next(r for r in records if r.component == "brew-deps" and r.name == "voice")
    assert bd.status == "missing"
    assert "whisper-cpp" in (bd.detail or "")
    assert "whisper-cli" not in (bd.detail or ""), bd.detail  # binary stays internal


# ---- 18.13 pipx inject must use --force --include-apps ----

def test_pipx_inject_passes_force_and_include_apps():
    """Without --force, pipx skips already-injected packages and silently
    ignores --include-apps — leaving venv-bin scripts un-symlinked to
    ~/.local/bin. Both flags must appear in the inject argv."""
    import inspect
    from hermes.install.installer import step_plugin_packages
    src = inspect.getsource(step_plugin_packages)
    assert '"--include-apps"' in src, src
    assert '"--force"' in src, src


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
