"""Tests for hermes.install.mcp_cli — the `claude mcp` adapter, exercised
against a faked claude binary.

    PYTHONPATH=src python3 tests/test_mcp_cli.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_claude import write_fake_claude  # noqa: E402
from hermes.install import mcp_cli  # noqa: E402


def _cli(d: Path) -> mcp_cli.McpCli:
    home = d / "home"; cwd = d / "proj"
    home.mkdir(); cwd.mkdir()
    binary = write_fake_claude(d / "bin")
    return mcp_cli.McpCli(binary=binary, home=str(home), cwd=str(cwd))


def test_claude_bin_override_wins():
    os.environ["HERMES_CLAUDE_BIN"] = "/some/explicit/claude"
    try:
        assert mcp_cli.claude_bin() == "/some/explicit/claude"
    finally:
        os.environ.pop("HERMES_CLAUDE_BIN", None)


def test_add_user_scope_top_level():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        cli = _cli(d)
        ok, _ = cli.add("voice", "hermes-voice", [], {"VOICE_CLOUD_MODE": "off"}, "user")
        assert ok
        data = json.loads((d / "home" / ".claude.json").read_text())
        assert "voice" in data["mcpServers"]
        assert data["mcpServers"]["voice"]["env"]["VOICE_CLOUD_MODE"] == "off"


def test_add_local_scope_under_project():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        cli = _cli(d)
        ok, _ = cli.add("telegram-bot", "hermes-telegram-bot", [], {"X": "y"}, "local")
        assert ok
        data = json.loads((d / "home" / ".claude.json").read_text())
        # not at top level — under some projects[<cwd>] entry (the exact key is
        # the realpath of cwd, which on macOS differs via /tmp -> /private/tmp).
        assert "telegram-bot" not in (data.get("mcpServers") or {})
        under_project = any(
            "telegram-bot" in (p.get("mcpServers") or {})
            for p in (data.get("projects") or {}).values())
        assert under_project, data


def test_is_registered_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        cli = _cli(d)
        assert not cli.is_registered("voice")
        cli.add("voice", "hermes-voice", [], {}, "user")
        assert cli.is_registered("voice")


def test_add_with_missing_binary_returns_error():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        cli = mcp_cli.McpCli(binary=str(Path(d) / "nope"), home=str(d), cwd=str(d))
        ok, msg = cli.add("x", "cmd", [], {}, "user")
        assert not ok
        assert msg  # surfaces the error


def test_manual_add_command_omits_secret_values():
    cmd = mcp_cli.manual_add_command(
        "telegram-bot", "hermes-telegram-bot", [],
        {"TELEGRAM_BOT_TOKEN": "supersecret"}, "local")
    assert "supersecret" not in cmd
    assert "claude mcp add -s local telegram-bot hermes-telegram-bot" in cmd
    assert "-e TELEGRAM_BOT_TOKEN=…" in cmd


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
