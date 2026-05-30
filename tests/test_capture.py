"""Tests for hermes.capture — synthetic ~/.claude, no-secret-leak assertions.

    PYTHONPATH=src python3 tests/test_capture.py
    python3 -m pytest tests/test_capture.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hermes.capture import capture  # noqa: E402
from hermes.manifest import Manifest  # noqa: E402

_SECRET = "sk-ant-abcdef0123456789ABCDEF0123456789"
_TG_TOKEN = "123456789:AAEdefGhIjKlMnOpQrStUvWxYz012345678"


def _make_fake_claude(home: Path) -> None:
    claude = home / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("# global instructions\n")
    settings = {
        "permissions": {"allow": ["Bash(*)"]},
        "mcpServers": {
            "telegram-bot": {
                "command": "hermes-telegram",
                "args": ["--poll"],
                "env": {"TELEGRAM_BOT_TOKEN": _TG_TOKEN},
            }
        },
        "hooks": {"Stop": [{"matcher": "", "hooks": [{"type": "command", "command": "x"}]}]},
        "someApiKey": _SECRET,
    }
    (claude / "settings.json").write_text(json.dumps(settings))
    # local skill
    skill = claude / "skills" / "foo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# foo skill\n")
    # plugins
    plugins = claude / "plugins"
    plugins.mkdir(parents=True)
    (plugins / "installed_plugins.json").write_text(json.dumps({
        "version": 2,
        "plugins": {"mempalace@mempalace": [{"version": "3.0.14", "scope": "user"}]},
    }))
    # ephemerals that MUST be ignored
    (claude / "projects").mkdir()
    (claude / "projects" / "leak.json").write_text(json.dumps({"token": _SECRET}))
    (claude / "history.jsonl").write_text(_SECRET + "\n")
    (claude / "settings.local.json").write_text(json.dumps({"localSecret": _SECRET}))


def _all_manifest_text(repo: Path) -> str:
    chunks = []
    for p in (repo / "manifest").rglob("*"):
        if p.is_file():
            chunks.append(p.read_text(errors="ignore"))
    if (repo / "secrets.env.example").exists():
        chunks.append((repo / "secrets.env.example").read_text())
    return "\n".join(chunks)


def test_capture_basic_and_no_secret_leak():
    with tempfile.TemporaryDirectory() as d:
        home = Path(d) / "home"
        repo = Path(d) / "repo"
        home.mkdir()
        repo.mkdir()
        _make_fake_claude(home)

        result = capture(config_root=repo, home=home)

        # Manifest loads and reflects the source.
        m = Manifest.load(repo)
        assert m.has_settings
        # CLAUDE.md is user-managed and intentionally not captured.
        assert not (repo / "manifest" / "CLAUDE.md").exists()
        assert {s.name for s in m.skills} == {"foo"}
        assert next(s for s in m.skills if s.name == "foo").source == "local"
        assert {p.name for p in m.plugins} == {"mempalace"}
        assert {s.name for s in m.mcp_servers} == {"telegram-bot"}

        # MCP env is redacted to a placeholder, not the literal token.
        tg = next(s for s in m.mcp_servers if s.name == "telegram-bot")
        assert tg.env["TELEGRAM_BOT_TOKEN"].startswith("${")

        # The local skill files were copied.
        assert (repo / "manifest" / "skills" / "foo" / "files" / "SKILL.md").exists()

        # secrets.env.example lists discovered vars.
        example = (repo / "secrets.env.example").read_text()
        assert "TELEGRAM_BOT_TOKEN=" in example

        # CRITICAL: no literal secret appears anywhere under manifest/.
        blob = _all_manifest_text(repo)
        assert _SECRET not in blob, "raw API key leaked into manifest"
        assert _TG_TOKEN not in blob, "raw Telegram token leaked into manifest"

        # Ephemeral content was never read.
        assert "leak.json" not in blob
        assert not (repo / "manifest" / "projects").exists()


def test_capture_dry_run_writes_nothing():
    with tempfile.TemporaryDirectory() as d:
        home = Path(d) / "home"
        repo = Path(d) / "repo"
        home.mkdir()
        repo.mkdir()
        _make_fake_claude(home)

        result = capture(config_root=repo, home=home, dry_run=True)
        assert result.actions, "dry-run should still report planned actions"
        assert not (repo / "manifest").exists(), "dry-run must not write the manifest"
        assert not (repo / "secrets.env.example").exists()


def test_capture_only_and_skip():
    with tempfile.TemporaryDirectory() as d:
        home = Path(d) / "home"
        repo = Path(d) / "repo"
        home.mkdir()
        repo.mkdir()
        _make_fake_claude(home)

        result = capture(config_root=repo, home=home, only=["skills"])
        m = Manifest.load(repo)
        assert {s.name for s in m.skills} == {"foo"}
        assert m.plugins == []  # plugins skipped


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
