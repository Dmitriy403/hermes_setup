"""install.sh — syntax + HERMES_CONFIG_URL flow with mocked git/hermes/pipx.

Validates that setting HERMES_CONFIG_URL clones the config repo, routes secrets
into it (not the tool repo), and invokes `hermes install --manifest-dir <that>`.

    python3 tests/test_install_sh.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INSTALL_SH = REPO / "install.sh"


def test_install_sh_syntax():
    subprocess.run(["bash", "-n", str(INSTALL_SH)], check=True)


def test_install_sh_existing_checkout_uses_reset_hard():
    """`pull --ff-only` silently fails on shallow-clone graft points, leaving
    the tool clone on stale code; the installer owns this directory and must
    force-sync it to origin via `reset --hard` instead."""
    body = INSTALL_SH.read_text()
    assert 'reset --hard "origin/$HERMES_REPO_REF"' in body, "reset --hard missing"
    # Any remaining `pull --ff-only` is for the user-owned config repo and
    # must surface failures rather than `|| true` them.
    lines = body.splitlines()
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("#") or "pull --ff-only" not in stripped:
            continue
        # The invocation must NOT end with `|| true` (silent), but should fall
        # through to a `warn` (either on the same line or continued via `\`).
        joined = stripped
        j = i
        while joined.rstrip().endswith("\\") and j + 1 < len(lines):
            j += 1
            joined = joined.rstrip()[:-1] + " " + lines[j].lstrip()
        assert "|| true" not in joined, f"silent ff-only pull: {joined!r}"
        assert "warn" in joined, f"ff-only pull must surface failure: {joined!r}"


def _write_stub(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


def test_install_sh_config_url_routes_secrets_and_passes_manifest_dir():
    """HERMES_CONFIG_URL set → secrets land in the cloned config dir and
    hermes install is called with --manifest-dir <that dir>."""
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        binp = dd / "bin"; binp.mkdir()
        # Fake git: on `git clone --depth 1 <url> <dst>`, create dst and a
        # minimal manifest fixture; every other invocation is a no-op.
        _write_stub(binp / "git", (
            '#!/bin/sh\n'
            'if [ "$1" = "clone" ]; then\n'
            '  shift\n'
            '  while [ "${1#-}" != "$1" ]; do\n'   # strip leading flags (e.g. --depth, --branch)
            '    case "$1" in --*=*) shift;; -*) shift; shift;; *) break;; esac\n'
            '  done\n'
            '  url="$1"; dst="$2"\n'
            '  mkdir -p "$dst/.git" "$dst/manifest"\n'
            '  : > "$dst/.git/HEAD"\n'
            '  printf "%s\\n" \\\n'
            '    "schema_version: 1" "skills: []" "mcp_servers: []" \\\n'
            '    "commands: []" "hooks: []" \\\n'
            '    "files:" "  claude_md: false" "  settings: false" "  keybindings: false" \\\n'
            '    > "$dst/manifest/hermes.yaml"\n'
            'fi\nexit 0\n'))
        # Fake hermes: log its argv so the test can inspect what install.sh invoked.
        log = dd / "hermes-args.log"
        _write_stub(binp / "hermes", f'#!/bin/sh\nprintf "%s\\n" "$@" > "{log}"\n')
        # Other tools the script touches: stubs returning 0.
        for n in ("pipx", "brew", "npm", "claude"):
            _write_stub(binp / n, "#!/bin/sh\nexit 0\n")

        env = dict(os.environ)
        env["PATH"] = f"{binp}:/usr/bin:/bin"
        env["HOME"] = str(dd / "home"); (dd / "home").mkdir()

        # Pre-stage the tool checkout so the script takes the "update existing"
        # branch and never tries to actually fetch from a remote.
        tool = dd / "tool"
        (tool / ".git").mkdir(parents=True); (tool / "manifest").mkdir()
        # secrets.env.example in the tool would be unused here (config dir wins).
        env["HERMES_HOME_DIR"] = str(tool)
        env["HERMES_REPO_URL"] = "stub://tool"

        # The unit under test:
        env["HERMES_CONFIG_URL"] = "stub://config"
        env["HERMES_CONFIG_DIR"] = str(dd / "cfg")
        env["HERMES_NONINTERACTIVE"] = "1"

        # A user-provided secrets file routes to the config dir.
        sf = dd / "src-secrets.env"
        sf.write_text("RESTIC_PASSWORD=test-only-not-real\n")
        env["HERMES_SECRETS_FILE"] = str(sf)

        out = subprocess.run(["bash", str(INSTALL_SH)], env=env,
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, f"install.sh failed:\nSTDOUT:\n{out.stdout}\nSTDERR:\n{out.stderr}"

        # Secrets routed to the CONFIG dir, not the tool dir.
        cfg_secrets = dd / "cfg" / "secrets.env"
        assert cfg_secrets.exists(), out.stdout + out.stderr
        assert "RESTIC_PASSWORD=test-only-not-real" in cfg_secrets.read_text()
        assert not (tool / "secrets.env").exists(), "secrets must NOT land in the tool repo"

        # hermes was called with --manifest-dir <cfg dir>.
        assert log.exists(), "hermes was never invoked"
        argv = log.read_text().splitlines()
        assert argv[0] == "install"
        assert "--manifest-dir" in argv
        assert str(dd / "cfg") in argv


def test_install_sh_factory_path_keeps_secrets_in_tool_repo():
    """HERMES_CONFIG_URL UNSET → factory path: hermes install (no flag), and any
    HERMES_SECRETS_FILE lands in the tool repo (legacy behavior preserved)."""
    with tempfile.TemporaryDirectory() as d:
        dd = Path(d)
        binp = dd / "bin"; binp.mkdir()
        _write_stub(binp / "git", "#!/bin/sh\nexit 0\n")
        log = dd / "hermes-args.log"
        _write_stub(binp / "hermes", f'#!/bin/sh\nprintf "%s\\n" "$@" > "{log}"\n')
        for n in ("pipx", "brew", "npm", "claude"):
            _write_stub(binp / n, "#!/bin/sh\nexit 0\n")

        env = dict(os.environ)
        env["PATH"] = f"{binp}:/usr/bin:/bin"
        env["HOME"] = str(dd / "home"); (dd / "home").mkdir()
        tool = dd / "tool"
        (tool / ".git").mkdir(parents=True); (tool / "manifest").mkdir()
        env["HERMES_HOME_DIR"] = str(tool)
        env["HERMES_REPO_URL"] = "stub://tool"
        env["HERMES_NONINTERACTIVE"] = "1"

        sf = dd / "src-secrets.env"; sf.write_text("X=y\n")
        env["HERMES_SECRETS_FILE"] = str(sf)
        env.pop("HERMES_CONFIG_URL", None)

        out = subprocess.run(["bash", str(INSTALL_SH)], env=env,
                             capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stdout + out.stderr
        assert (tool / "secrets.env").exists()
        assert log.exists()
        argv = log.read_text().splitlines()
        assert argv == ["install"], argv  # no --manifest-dir on the factory path


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
    sys.exit(_run_standalone())
