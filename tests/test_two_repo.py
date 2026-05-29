"""Tests for §18 — two-repo support: manifest_dir/tool_root split, $HOME
templating round-trip, permission-cruft pruning, capture isolation.

    PYTHONPATH=src python3 tests/test_two_repo.py
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hermes import paths  # noqa: E402
from hermes.capture import capture  # noqa: E402
from hermes.install.installer import install  # noqa: E402

_TG = "123456789:AAEdefGhIjKlMnOpQrStUvWxYz012345678"


# ---- 18.1 / config_root resolution precedence ----

def test_config_root_precedence():
    with tempfile.TemporaryDirectory() as d:
        explicit = Path(d) / "explicit"
        env = Path(d) / "env"
        explicit.mkdir(); env.mkdir()
        old = os.environ.get("HERMES_MANIFEST_DIR")
        try:
            os.environ["HERMES_MANIFEST_DIR"] = str(env)
            # explicit override beats env
            assert paths.config_root(str(explicit)) == explicit.resolve()
            # env beats default
            assert paths.config_root() == env.resolve()
        finally:
            if old is None:
                os.environ.pop("HERMES_MANIFEST_DIR", None)
            else:
                os.environ["HERMES_MANIFEST_DIR"] = old


# ---- 18.3 / $HOME templating ----

def test_template_expand_roundtrip():
    p = "/Users/alice/.local/bin/x"
    templated = paths.template_home(p, "/Users/alice")
    assert templated == "${HOME}/.local/bin/x"
    # expand to a DIFFERENT home → portable
    assert paths.expand_home(templated, "/Users/bob") == "/Users/bob/.local/bin/x"


def _src_claude(home: Path, *, hook_home: str) -> None:
    claude = home / ".claude"
    claude.mkdir(parents=True)
    (claude / "CLAUDE.md").write_text("# g\n")
    (claude / "settings.json").write_text(json.dumps({
        "permissions": {"allow": [
            "Bash(*)",
            f"Bash(mkdir -p {hook_home}/.claude/skills/foo)",  # transient cruft
        ]},
        "hooks": {"SessionStart": [{"matcher": "", "hooks": [
            {"type": "command", "command": f"{hook_home}/.local/bin/mempalace hook run"}]}]},
    }))
    (claude / "plugins").mkdir()
    (claude / "plugins" / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {}}))


def test_capture_templates_home_and_prunes_then_install_expands():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        src_home = d / "srchome"      # the captured machine's home
        cfg = d / "hermes_config"     # private config repo
        tool = d / "hermes_setup"     # public tool repo
        tgt_home = d / "tgthome"      # a DIFFERENT target home
        for p in (src_home, cfg, tool, tgt_home):
            p.mkdir()
        _src_claude(src_home, hook_home=str(src_home))

        # capture into the config repo, with src_home as the home being captured
        capture(config_root=cfg, home=src_home)

        committed = (cfg / "manifest" / "settings.json").read_text()
        # $HOME templated: the source home path is gone, ${HOME} present
        assert str(src_home) not in committed
        assert "${HOME}/.local/bin/mempalace" in committed
        # transient Bash(mkdir …) grant pruned
        assert "mkdir" not in committed

        # set up the tool repo (probe stub + permissions) for install
        (tool / "bin").mkdir()
        probe = tool / "bin" / "hermes-probe-tcc"
        probe.write_text("#!/bin/sh\n")
        probe.chmod(probe.stat().st_mode | stat.S_IXUSR)
        (tool / "manifest").mkdir()
        (tool / "manifest" / "permissions.yaml").write_text("schema_version: 1\n")

        # install the config onto a DIFFERENT home; ${HOME} must expand to it
        install(config_root=cfg, home=tgt_home, tool_root=tool)
        installed = (tgt_home / ".claude" / "settings.json").read_text()
        assert f"{tgt_home}/.local/bin/mempalace" in installed
        assert "${HOME}" not in installed
        assert str(src_home) not in installed   # no leak of the capture machine's home


# ---- 18.2 / capture isolation: writing config doesn't touch tool_root ----

def test_capture_into_manifest_dir_isolated_from_tool():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        src_home = d / "srchome"
        cfg = d / "cfg"
        tool = d / "tool"
        for p in (src_home, cfg, tool):
            p.mkdir()
        (tool / "manifest").mkdir()  # pretend factory defaults live here
        _src_claude(src_home, hook_home=str(src_home))

        capture(config_root=cfg, home=src_home)

        # config repo got the manifest; tool repo's manifest/ is untouched
        assert (cfg / "manifest" / "settings.json").exists()
        assert list((tool / "manifest").iterdir()) == []


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
