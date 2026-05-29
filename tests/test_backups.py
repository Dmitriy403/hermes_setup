"""Tests for backups — destination resolution, restic argv, exclude merge,
notify routing, launchd plist, and CLI fail-soft when restic is absent.

No restic/rclone needed (live edge).

    PYTHONPATH=src python3 tests/test_backups.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))

from backups import core, launchd, notify  # noqa: E402


# ---- destination resolution ----

def test_destination_local_and_external():
    assert core.destination_repo({"kind": "local", "path": "/tmp/r"}) == "/tmp/r"
    assert core.destination_repo({"kind": "external_disk", "path": "/Volumes/X/r"}) == "/Volumes/X/r"


def test_destination_rclone():
    d = {"kind": "rclone:b2_personal", "repo": "hermes-backups"}
    assert core.destination_repo(d) == "rclone:b2_personal:hermes-backups"
    # default repo name
    assert core.destination_repo({"kind": "rclone:gdrive"}) == "rclone:gdrive:hermes-backups"


def test_destination_local_requires_path():
    try:
        core.destination_repo({"kind": "local"})
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError when local destination has no path")


# ---- argv ----

def test_backup_argv_excludes_and_dryrun():
    argv = core.backup_argv("/repo", ["/a", "/b"], ["**/node_modules", "**/.git/objects"], dry_run=True)
    assert argv[:4] == ["restic", "-r", "/repo", "backup"]
    assert "/a" in argv and "/b" in argv
    assert argv.count("--exclude") == 2
    assert "--dry-run" in argv


def test_check_and_restore_argv():
    assert core.check_argv("/repo") == ["restic", "-r", "/repo", "check"]
    r = core.restore_argv("/repo", "/tmp/out", path="~/Documents", snapshot="abc123")
    assert r[:5] == ["restic", "-r", "/repo", "restore", "abc123"]
    assert "--target" in r and "--include" in r
    # default snapshot = latest, no include
    r2 = core.restore_argv("/repo", "/tmp/out")
    assert "latest" in r2 and "--include" not in r2


# ---- exclude merge ----

def test_merge_excludes():
    merged = core.merge_excludes(["custom/x"], "extra1:extra2")
    assert "**/node_modules" in merged          # default
    assert "custom/x" in merged                  # manifest
    assert "extra1" in merged and "extra2" in merged  # env
    # idempotent (no dupes)
    assert merged.count("**/node_modules") == 1


def test_collect_sources_and_excludes():
    cfg = {
        "sources": [
            {"path": "~/.hermes_setup"},
            {"path": "~/.claude", "excludes": ["**/sessions"]},
            "~/Documents",
        ],
        "excludes": ["top-level-x"],
    }
    sources, excludes = core.collect_sources_and_excludes(cfg)
    assert sources == ["~/.hermes_setup", "~/.claude", "~/Documents"]
    assert "**/sessions" in excludes and "top-level-x" in excludes
    assert "**/node_modules" in excludes  # defaults included


# ---- notify routing (pure) ----

def test_notifier_names():
    assert notify.notifier_names({}) == ["mac"]
    assert notify.notifier_names({"BACKUP_ALERT_CHAT_ID": "1"}) == ["mac"]  # needs token too
    assert notify.notifier_names({"BACKUP_ALERT_CHAT_ID": "1", "TELEGRAM_BOT_TOKEN": "t"}) == ["mac", "telegram"]


def test_notify_failure_never_raises():
    calls = []
    def good(t, m): calls.append(("good", t))
    def bad(t, m): raise RuntimeError("boom")
    status = notify.notify_failure("FAILED", "summary", {"mac": good, "telegram": bad})
    assert status["mac"] == "sent"
    assert status["telegram"].startswith("failed:")
    assert ("good", "FAILED") in calls


# ---- launchd ----

def test_periodic_plist():
    xml = launchd.backup_plist("/usr/local/bin/hermes-backup", interval_seconds=3600, stderr_path="/tmp/b.log")
    assert "com.hermes.backup" in xml
    assert "<key>StartInterval</key>" in xml and "3600" in xml
    assert "/tmp/b.log" in xml


# ---- CLI fail-soft (restic absent here) ----

def test_cli_backup_fail_soft_without_restic():
    from backups import cli
    if core.restic_binary() is not None:
        return  # restic installed — skip the absent-path assertion
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d) / "backups.yaml"
        cfg.write_text("schema_version: 1\nsources: [\"~/x\"]\ndestination: {kind: local, path: /tmp/r}\n")
        rc = cli.main(["--config", str(cfg), "backup"])
        assert rc == 10  # missing_dependency exit


# ---- live e2e round-trip (needs restic installed) ----

def test_e2e_backup_restore_roundtrip():
    import os
    import subprocess
    if core.restic_binary() is None:
        return  # live edge — skip when restic absent
    from backups import cli
    prev_pw = os.environ.get("RESTIC_PASSWORD")
    os.environ["RESTIC_PASSWORD"] = "hermes-test-passphrase"
    try:
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            src = root / "src"
            (src / "nested").mkdir(parents=True)
            (src / "a.txt").write_bytes(b"hello hermes\n")
            (src / "nested" / "b.bin").write_bytes(bytes(range(256)) * 4)
            # an excluded path must NOT come back
            (src / "node_modules").mkdir()
            (src / "node_modules" / "junk.txt").write_bytes(b"should be excluded")

            repo = root / "repo"
            subprocess.run(["restic", "-r", str(repo), "init"], check=True, capture_output=True)

            cfg = root / "backups.yaml"
            cfg.write_text(
                "schema_version: 1\n"
                f"sources:\n  - path: {src}\n"
                f"destination: {{kind: local, path: {repo}}}\n"
            )
            assert cli.main(["--config", str(cfg), "backup"]) == 0

            out = root / "out"
            assert cli.main(["--config", str(cfg), "restore", "--target", str(out)]) == 0

            # restic restores under the original absolute path beneath --target
            restored = out / str(src).lstrip("/")
            assert (restored / "a.txt").read_bytes() == b"hello hermes\n"
            assert (restored / "nested" / "b.bin").read_bytes() == bytes(range(256)) * 4
            assert not (restored / "node_modules").exists()  # default exclude held

            assert cli.main(["--config", str(cfg), "verify"]) == 0
    finally:
        if prev_pw is None:
            os.environ.pop("RESTIC_PASSWORD", None)
        else:
            os.environ["RESTIC_PASSWORD"] = prev_pw


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
