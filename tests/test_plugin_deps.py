"""Tests for doctor plugin-dependency check (§16.17 / Decision 18)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hermes.doctor import plugin_deps as pd  # noqa: E402


def test_check_returns_entries_for_known_plugins():
    deps = pd.check_plugin_deps()
    names = {(d.plugin, d.name) for d in deps}
    assert ("voice", "whisper.cpp") in names
    assert ("voice", "ffmpeg") in names
    assert ("backups", "restic") in names
    assert ("backups", "rclone") in names


def test_render_lists_brew_for_missing():
    deps = [
        pd.DepStatus(plugin="voice", name="ffmpeg", present=False, found_at=None, brew="ffmpeg"),
        pd.DepStatus(plugin="backups", name="restic", present=True, found_at="/opt/homebrew/bin/restic", brew="restic"),
    ]
    out = pd.render(deps)
    assert "brew install ffmpeg" in out
    assert "brew install restic" not in out  # present → no install hint
    assert "MISSING" in out


def test_render_all_present():
    deps = [pd.DepStatus(plugin="backups", name="restic", present=True, found_at="/x/restic", brew="restic")]
    out = pd.render(deps)
    assert "All plugin dependencies present." in out


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
