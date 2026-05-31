"""Tests for hermes.verify — capture→install→verify is clean; drift detected.

    PYTHONPATH=src python3 tests/test_verify.py
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_claude import write_fake_claude  # noqa: E402
from hermes.capture import capture  # noqa: E402
from hermes.install.installer import install  # noqa: E402
from hermes.verify import has_drift, verify  # noqa: E402

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
    (plugins / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {}}))


def _setup(d: Path):
    src, repo, tgt = d / "src", d / "repo", d / "tgt"
    for p in (src, repo, tgt):
        p.mkdir()
    _make_source_claude(src)
    capture(config_root=repo, home=src)
    bindir = repo / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    probe = bindir / "hermes-probe-tcc"
    probe.write_text("#!/bin/sh\n")
    probe.chmod(probe.stat().st_mode | stat.S_IXUSR)
    # Fake claude so install registers MCP into <tgt>/.claude.json and verify
    # finds it there (never touches the real ~/.claude.json).
    os.environ["HERMES_CLAUDE_BIN"] = write_fake_claude(bindir)
    (repo / "secrets.env").write_text(f"TELEGRAM_BOT_TOKEN={_TG_TOKEN}\n")
    (repo / "manifest" / "permissions.yaml").write_text(
        "schema_version: 1\nsecurity:\n  layer_b:\n    enabled: false\n")
    os.environ.pop("TELEGRAM_BOT_TOKEN", None)
    return src, repo, tgt


def test_capture_install_verify_is_clean():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        src, repo, tgt = _setup(d)
        install(config_root=repo, home=tgt, tool_root=repo)
        records = verify(config_root=repo, home=tgt, tool_root=repo)
        drifted = [r for r in records if r.status != "match"]
        assert not drifted, f"expected zero drift, got: {drifted}"
        assert not has_drift(records)


def test_verify_detects_modified_file():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        src, repo, tgt = _setup(d)
        install(config_root=repo, home=tgt, tool_root=repo)
        # Tamper with the installed skill file (the remaining `verbatim`
        # surface — CLAUDE.md is no longer managed by hermes).
        skill_md = tgt / ".claude" / "skills" / "foo" / "SKILL.md"
        skill_md.write_text("# tampered\n")
        records = verify(config_root=repo, home=tgt, tool_root=repo)
        cm = next(r for r in records if r.component == "skill" and r.name == "foo")
        assert cm.status == "modified", cm


def test_verify_detects_missing_and_extra_skill():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        src, repo, tgt = _setup(d)
        install(config_root=repo, home=tgt, tool_root=repo)
        # Remove the installed skill → missing; add an unmanaged one → extra.
        import shutil
        shutil.rmtree(tgt / ".claude" / "skills" / "foo")
        (tgt / ".claude" / "skills" / "rogue").mkdir(parents=True)
        records = verify(config_root=repo, home=tgt, tool_root=repo)
        statuses = {(r.name, r.status) for r in records if r.component == "skill"}
        assert ("foo", "missing") in statuses, statuses
        assert ("rogue", "extra") in statuses, statuses


def test_verify_detects_plugin_version_drift():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        src, repo, tgt = _setup(d)
        # manifest has no plugins (source had none); add one to the manifest and
        # install a different version on the target to force drift.
        from hermes.manifest import Manifest, PluginEntry
        m = Manifest.load(repo)
        m.plugins = [PluginEntry(name="mempalace", marketplace="mempalace", version="3.0.14")]
        m.save(repo)
        (tgt / ".claude" / "plugins").mkdir(parents=True)
        (tgt / ".claude" / "plugins" / "installed_plugins.json").write_text(json.dumps({
            "version": 2,
            "plugins": {"mempalace@mempalace": [{"version": "2.0.0"}]},
        }))
        records = verify(config_root=repo, home=tgt, tool_root=repo)
        pl = next(r for r in records if r.component == "plugin" and r.name == "mempalace")
        assert pl.status == "modified", pl


def test_verify_mcp_registered_is_match():
    """After install, the manifest MCP server is registered in ~/.claude.json
    and verify reports the `mcp` component as match."""
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        src, repo, tgt = _setup(d)
        install(config_root=repo, home=tgt, tool_root=repo)
        records = verify(config_root=repo, home=tgt, tool_root=repo)
        mc = next(r for r in records if r.component == "mcp" and r.name == "tg")
        assert mc.status == "match", mc


def test_verify_flags_settings_json_only_mcp_as_drift():
    """Regression (the bug class): a server present ONLY in settings.json's
    mcpServers map must NOT be treated as registered — Claude Code ignores it
    there. verify must report the `mcp` component as drift (not match)."""
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        src, repo, tgt = _setup(d)
        install(config_root=repo, home=tgt, tool_root=repo)
        # Simulate the old broken state: server only under settings.json, and
        # NOT in ~/.claude.json.
        (tgt / ".claude.json").write_text(json.dumps({"mcpServers": {}}))
        settings_path = tgt / ".claude" / "settings.json"
        settings = json.loads(settings_path.read_text())
        settings["mcpServers"] = {"tg": {"command": "tgbot", "args": [], "env": {}}}
        settings_path.write_text(json.dumps(settings))
        records = verify(config_root=repo, home=tgt, tool_root=repo)
        mc = next(r for r in records if r.component == "mcp" and r.name == "tg")
        assert mc.status != "match", "settings.json-only server must not count as registered"


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
