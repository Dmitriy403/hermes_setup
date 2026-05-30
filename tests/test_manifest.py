"""Tests for hermes.manifest — round-trip, env resolution, malformed handling.

Runnable two ways:
    python3 -m pytest tests/test_manifest.py
    PYTHONPATH=src python3 tests/test_manifest.py      (no pytest needed)
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hermes.manifest import (  # noqa: E402
    Manifest,
    ManifestError,
    McpServer,
    PluginEntry,
    SkillEntry,
    parse_secrets_env,
    resolve_manifest_env,
)


def _sample() -> Manifest:
    return Manifest(
        claude_version="1.2.3",
        skills=[
            SkillEntry(name="vision", source="local"),
            SkillEntry(name="review", source="git", repo="https://x/y", ref="main"),
            SkillEntry(name="mine", source="marketplace", marketplace="mempalace", version="0.4"),
        ],
        plugins=[PluginEntry(name="mempalace", marketplace="mempalace", version="1.0")],
        mcp_servers=[
            McpServer(name="telegram-bot", command="hermes-telegram",
                      args=["--poll"], env={"TELEGRAM_BOT_TOKEN": "${TELEGRAM_BOT_TOKEN}"}),
            McpServer(name="mempalace", command="mempalace", args=["mcp"], env={}),
        ],
        commands=["foo", "bar"],
        hooks=["stop.sh"],
        has_settings=True,
        has_keybindings=False,
    )


def test_round_trip_is_fixed_point():
    m = _sample()
    with tempfile.TemporaryDirectory() as d:
        m.save(d)
        loaded = Manifest.load(d)
        # Re-save and compare the on-disk bytes — must be stable.
        first = (Path(d) / "manifest" / "hermes.yaml").read_text()
        loaded.save(d)
        second = (Path(d) / "manifest" / "hermes.yaml").read_text()
        assert first == second, "hermes.yaml not byte-stable across re-save"

    # Structural equality of the key fields.
    assert loaded.claude_version == m.claude_version
    assert {s.name for s in loaded.skills} == {s.name for s in m.skills}
    assert {s.name for s in loaded.mcp_servers} == {s.name for s in m.mcp_servers}
    assert {p.name for p in loaded.plugins} == {p.name for p in m.plugins}
    assert sorted(loaded.commands) == sorted(m.commands)
    assert loaded.has_settings and not loaded.has_keybindings
    # MCP env placeholder survives round-trip unresolved.
    tg = next(s for s in loaded.mcp_servers if s.name == "telegram-bot")
    assert tg.env["TELEGRAM_BOT_TOKEN"] == "${TELEGRAM_BOT_TOKEN}"


def test_env_resolution_reports_missing():
    m = _sample()
    resolved, missing = resolve_manifest_env(m, environ={}, secrets={})
    assert missing == ["TELEGRAM_BOT_TOKEN"]
    # Unresolved placeholder is left intact.
    tg = next(s for s in resolved.mcp_servers if s.name == "telegram-bot")
    assert tg.env["TELEGRAM_BOT_TOKEN"] == "${TELEGRAM_BOT_TOKEN}"


def test_env_resolution_environ_wins_over_secrets():
    m = _sample()
    resolved, missing = resolve_manifest_env(
        m, environ={"TELEGRAM_BOT_TOKEN": "from-environ"},
        secrets={"TELEGRAM_BOT_TOKEN": "from-secrets"},
    )
    assert missing == []
    tg = next(s for s in resolved.mcp_servers if s.name == "telegram-bot")
    assert tg.env["TELEGRAM_BOT_TOKEN"] == "from-environ"


def test_secrets_env_resolves_when_environ_absent():
    m = _sample()
    resolved, missing = resolve_manifest_env(
        m, environ={}, secrets={"TELEGRAM_BOT_TOKEN": "secret-val"},
    )
    assert missing == []
    tg = next(s for s in resolved.mcp_servers if s.name == "telegram-bot")
    assert tg.env["TELEGRAM_BOT_TOKEN"] == "secret-val"


def test_parse_secrets_env():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "secrets.env"
        p.write_text('# comment\nKEY1=value1\nKEY2 = "quoted value"\n\nBADLINE\n')
        parsed = parse_secrets_env(p)
        assert parsed == {"KEY1": "value1", "KEY2": "quoted value"}


def test_missing_manifest_raises():
    with tempfile.TemporaryDirectory() as d:
        try:
            Manifest.load(d)
        except ManifestError:
            pass
        else:
            raise AssertionError("expected ManifestError for missing manifest")


def test_bad_schema_version_raises():
    with tempfile.TemporaryDirectory() as d:
        mdir = Path(d) / "manifest"
        mdir.mkdir()
        (mdir / "hermes.yaml").write_text("schema_version: 99\n")
        try:
            Manifest.load(d)
        except ManifestError as exc:
            assert "schema_version" in str(exc)
        else:
            raise AssertionError("expected ManifestError for bad schema_version")


def test_missing_mcp_sidecar_raises():
    with tempfile.TemporaryDirectory() as d:
        mdir = Path(d) / "manifest"
        mdir.mkdir()
        (mdir / "hermes.yaml").write_text(
            "schema_version: 1\nmcp_servers:\n  - ghost\n"
        )
        try:
            Manifest.load(d)
        except ManifestError as exc:
            assert "ghost" in str(exc)
        else:
            raise AssertionError("expected ManifestError for missing mcp sidecar")


def test_invalid_yaml_raises():
    with tempfile.TemporaryDirectory() as d:
        mdir = Path(d) / "manifest"
        mdir.mkdir()
        (mdir / "hermes.yaml").write_text("schema_version: 1\n  : : bad yaml : :\n")
        try:
            Manifest.load(d)
        except ManifestError:
            pass
        else:
            raise AssertionError("expected ManifestError for invalid YAML")


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
