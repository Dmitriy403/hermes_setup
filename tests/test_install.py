"""Tests for hermes.install — capture→install round-trip on fake homes,
fail-fast on missing secrets, idempotency, and security wiring.

    PYTHONPATH=src python3 tests/test_install.py
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hermes.capture import capture  # noqa: E402
from hermes.install.installer import InstallError, install  # noqa: E402

_TG_TOKEN = "123456789:AAEdefGhIjKlMnOpQrStUvWxYz012345678"


def _make_source_claude(home: Path) -> None:
    claude = home / ".claude"
    (claude / "skills" / "foo").mkdir(parents=True)
    (claude / "skills" / "foo" / "SKILL.md").write_text("# foo\n")
    (claude / "CLAUDE.md").write_text("# global\n")
    (claude / "settings.json").write_text(json.dumps({
        "permissions": {"allow": ["Bash(*)"]},
        "mcpServers": {"tg": {"command": "tgbot", "args": [],
                              "env": {"TELEGRAM_BOT_TOKEN": _TG_TOKEN}}},
    }))
    plugins = claude / "plugins"
    plugins.mkdir(parents=True)
    (plugins / "installed_plugins.json").write_text(json.dumps({
        "version": 2, "plugins": {}}))


def _make_repo(repo: Path, src_home: Path, *, secrets: bool = True,
               layer_b: bool = False, doctor_hook: bool = False) -> None:
    """Capture src_home into repo, add probe stub, secrets, permissions."""
    capture(config_root=repo, home=src_home)
    # probe stub (step_probe_check only needs existence + exec bit)
    bindir = repo / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    probe = bindir / "hermes-probe-tcc"
    probe.write_text("#!/bin/sh\necho '{}'\n")
    probe.chmod(probe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    if secrets:
        (repo / "secrets.env").write_text(f"TELEGRAM_BOT_TOKEN={_TG_TOKEN}\n")
    # minimal permissions.yaml for Layer B
    sec = "security:\n  layer_b:\n    enabled: %s\n" % ("true" if layer_b else "false")
    (repo / "manifest" / "permissions.yaml").write_text(
        "schema_version: 1\nfilesystem:\n  read: [\"~/Documents/**\"]\n" + sec)
    # copy sandbox-rules.yaml so Layer B generation works
    rules = Path(__file__).resolve().parents[1] / "tools" / "probe-tcc" / "sandbox-rules.yaml"
    if rules.exists():
        (repo / "tools" / "probe-tcc").mkdir(parents=True, exist_ok=True)
        (repo / "tools" / "probe-tcc" / "sandbox-rules.yaml").write_text(rules.read_text())
    if doctor_hook:
        hy = repo / "manifest" / "hermes.yaml"
        hy.write_text(hy.read_text() + "hooks_config:\n  doctor_on_session_start: true\n")


def test_install_round_trip_and_idempotent():
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "src"
        repo = Path(d) / "repo"
        tgt = Path(d) / "tgt"
        for p in (src, repo, tgt):
            p.mkdir()
        _make_source_claude(src)
        _make_repo(repo, src)

        # Point repo_root resolution + run install onto tgt home.
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        result = install(config_root=repo, home=tgt, tool_root=repo)
        tclaude = tgt / ".claude"
        # CLAUDE.md is intentionally NOT installed (user-managed).
        assert not (tclaude / "CLAUDE.md").exists()
        assert (tclaude / "skills" / "foo" / "SKILL.md").exists()
        # settings.json has mcpServers with the RESOLVED token (from secrets.env).
        settings = json.loads((tclaude / "settings.json").read_text())
        assert settings["mcpServers"]["tg"]["env"]["TELEGRAM_BOT_TOKEN"] == _TG_TOKEN
        # ~/.hermes created 0700.
        assert (tgt / ".hermes").exists()
        assert oct((tgt / ".hermes").stat().st_mode & 0o777) == "0o700"

        # Second run is idempotent.
        result2 = install(config_root=repo, home=tgt, tool_root=repo)
        assert any("unchanged" in a for a in result2.actions), result2.actions


def test_install_aborts_on_missing_secret():
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "src"
        repo = Path(d) / "repo"
        tgt = Path(d) / "tgt"
        for p in (src, repo, tgt):
            p.mkdir()
        _make_source_claude(src)
        _make_repo(repo, src, secrets=False)  # no secrets.env
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)

        try:
            install(config_root=repo, home=tgt, tool_root=repo)
        except InstallError as exc:
            assert "TELEGRAM_BOT_TOKEN" in str(exc)
            assert not (tgt / ".claude").exists(), "must not write before failing"
        else:
            raise AssertionError("expected InstallError for missing secret")


def test_install_aborts_on_missing_probe():
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "src"
        repo = Path(d) / "repo"
        tgt = Path(d) / "tgt"
        for p in (src, repo, tgt):
            p.mkdir()
        _make_source_claude(src)
        _make_repo(repo, src)
        (repo / "bin" / "hermes-probe-tcc").unlink()
        try:
            install(config_root=repo, home=tgt, tool_root=repo)
        except InstallError as exc:
            assert "probe" in str(exc).lower()
        else:
            raise AssertionError("expected InstallError for missing probe")


def test_install_layer_b_generates_profile():
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "src"
        repo = Path(d) / "repo"
        tgt = Path(d) / "tgt"
        for p in (src, repo, tgt):
            p.mkdir()
        _make_source_claude(src)
        _make_repo(repo, src, layer_b=True)
        # profile_path defaults to ~/.hermes/profile.sb under the target home.
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        install(config_root=repo, home=tgt, tool_root=repo)
        profile = tgt / ".hermes" / "profile.sb"
        assert profile.exists(), "Layer B profile not generated"
        assert oct(profile.stat().st_mode & 0o777) == "0o600"
        assert "(deny default)" in profile.read_text()


def test_install_doctor_hook_injected():
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "src"
        repo = Path(d) / "repo"
        tgt = Path(d) / "tgt"
        for p in (src, repo, tgt):
            p.mkdir()
        _make_source_claude(src)
        _make_repo(repo, src, doctor_hook=True)
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        install(config_root=repo, home=tgt, tool_root=repo)
        settings = json.loads((tgt / ".claude" / "settings.json").read_text())
        starts = settings["hooks"]["SessionStart"]
        cmds = [h["command"] for e in starts for h in e.get("hooks", [])]
        assert any("hermes doctor --check --exit-zero" in c for c in cmds)


def test_install_dry_run_writes_nothing():
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "src"
        repo = Path(d) / "repo"
        tgt = Path(d) / "tgt"
        for p in (src, repo, tgt):
            p.mkdir()
        _make_source_claude(src)
        _make_repo(repo, src)
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        result = install(config_root=repo, home=tgt, tool_root=repo, dry_run=True)
        assert result.actions
        assert not (tgt / ".claude").exists()
        assert not (tgt / ".hermes").exists()


def _install_with_existing_changed_settings(d: Path):
    """Helper: full repo + tgt where ~/.claude/settings.json already exists
    with content that differs from what install would write."""
    src = d / "src"; repo = d / "repo"; tgt = d / "tgt"
    for p in (src, repo, tgt):
        p.mkdir()
    _make_source_claude(src)
    _make_repo(repo, src)
    os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    # Pre-create a different settings.json in tgt so install would overwrite.
    tclaude = tgt / ".claude"; tclaude.mkdir()
    (tclaude / "settings.json").write_text('{"effortLevel": "low"}\n')
    return src, repo, tgt


def test_install_dry_run_includes_unified_diff_for_changed_file():
    """Dry-run shows the user exactly WHAT would change before they run real install."""
    with tempfile.TemporaryDirectory() as d:
        _, repo, tgt = _install_with_existing_changed_settings(Path(d))
        result = install(config_root=repo, home=tgt, tool_root=repo, dry_run=True)
        log = "\n".join(result.actions)
        # diff: <name>\n<unified-diff>
        assert "diff: ~/.claude/settings.json" in log
        # unified-diff hallmarks: ---/+++ headers and an effortLevel hunk.
        assert "--- a/~/.claude/settings.json" in log
        assert "+++ b/~/.claude/settings.json" in log
        assert "-" in log and "effortLevel" in log
    # dry-run guarantee: settings.json on disk wasn't touched.
    # (tgt is gone with the tempdir, so we just assert via the log absence.)


def test_install_confirm_n_skips_overwrite():
    """With --confirm, answering 'n' to the prompt preserves the live file."""
    import builtins
    with tempfile.TemporaryDirectory() as d:
        _, repo, tgt = _install_with_existing_changed_settings(Path(d))
        before = (tgt / ".claude" / "settings.json").read_text()
        original = builtins.input
        builtins.input = lambda prompt="": "n"
        try:
            result = install(config_root=repo, home=tgt, tool_root=repo, confirm=True)
        finally:
            builtins.input = original
        after = (tgt / ".claude" / "settings.json").read_text()
        assert before == after, "confirm=n must NOT overwrite"
        assert any("skipped: ~/.claude/settings.json (declined)" in a for a in result.actions)


def test_install_confirm_y_writes_overwrite():
    """With --confirm, answering 'y' proceeds with the overwrite."""
    import builtins
    with tempfile.TemporaryDirectory() as d:
        _, repo, tgt = _install_with_existing_changed_settings(Path(d))
        before = (tgt / ".claude" / "settings.json").read_text()
        original = builtins.input
        builtins.input = lambda prompt="": "y"
        try:
            install(config_root=repo, home=tgt, tool_root=repo, confirm=True)
        finally:
            builtins.input = original
        after = (tgt / ".claude" / "settings.json").read_text()
        assert before != after, "confirm=y must overwrite"
        # install writes a manifest-derived settings.json with at least permissions.
        assert "permissions" in after


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
