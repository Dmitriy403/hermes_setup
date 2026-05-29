"""Tests for macos_control.tools — structured returns, TCC mapping, command
construction. Real osascript/screencapture are NOT invoked (injected runner).

    PYTHONPATH=src python3 tests/test_macos_control.py
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

_TOOLS = (Path(__file__).resolve().parents[1] / "plugins" / "macos_control" / "tools.py")
_spec = importlib.util.spec_from_file_location("mc_tools", _TOOLS)
tools = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tools)


class FakeRunner:
    def __init__(self, code=0, out="", err=""):
        self.code, self.out, self.err = code, out, err
        self.calls: list[list[str]] = []

    def __call__(self, cmd):
        self.calls.append(cmd)
        return self.code, self.out, self.err


def test_classify_tcc_error():
    assert tools.classify_tcc_error("execution error: ... (-1743)") == "Automation"
    assert tools.classify_tcc_error("osascript is not allowed assistive access. (-25211)") == "Accessibility"
    assert tools.classify_tcc_error("some other error") is None


def test_focus_app_success():
    r = FakeRunner(0, "", "")
    res = tools.focus_app("Safari", runner=r)
    assert res == {"ok": True, "focused": "Safari"}
    assert r.calls[0][0] == "osascript"
    assert 'tell application "Safari" to activate' in r.calls[0][2]


def test_focus_app_automation_denied():
    r = FakeRunner(1, "", "execution error: Not authorized to send Apple events (-1743)")
    res = tools.focus_app("Safari", runner=r)
    assert res["ok"] is False
    assert res["error"] == "missing_permission"
    assert res["needed"] == "Automation"
    assert "Privacy_Automation" in res["how_to_fix"]


def test_list_windows_parses_tab_separated():
    r = FakeRunner(0, "Safari\tStart Page\nFinder\tDownloads\n", "")
    res = tools.list_windows(runner=r)
    assert res["ok"] is True
    assert {"app": "Safari", "title": "Start Page"} in res["windows"]
    assert {"app": "Finder", "title": "Downloads"} in res["windows"]


def test_list_windows_accessibility_denied():
    r = FakeRunner(1, "", "System Events got an error: osascript is not allowed assistive access. (-25211)")
    res = tools.list_windows(runner=r)
    assert res["error"] == "missing_permission"
    assert res["needed"] == "Accessibility"


def test_type_text_escapes_quotes():
    r = FakeRunner(0, "", "")
    res = tools.type_text('say "hi"', runner=r)
    assert res == {"ok": True, "typed": len('say "hi"')}
    assert '\\"hi\\"' in r.calls[0][2]


def test_key_combo_builds_modifiers():
    r = FakeRunner(0, "", "")
    res = tools.key_combo("cmd+shift+a", runner=r)
    assert res["ok"] is True
    script = r.calls[0][2]
    assert "command down" in script and "shift down" in script
    assert 'keystroke "a"' in script


def test_key_combo_rejects_multichar_key():
    r = FakeRunner(0, "", "")
    res = tools.key_combo("cmd+tab", runner=r)
    assert res["ok"] is False
    assert res["error"] == "unsupported_key"


def test_screenshot_full_command_and_result():
    r = FakeRunner(0, "", "")
    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / "s.png")
        res = tools.screenshot_full(path, runner=r)
        assert res["ok"] is True
        assert res["path"] == path
        assert r.calls[0][:2] == ["screencapture", "-x"]
        assert r.calls[0][-1] == path


def test_screenshot_region_builds_R_flag():
    r = FakeRunner(0, "", "")
    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / "s.png")
        tools.screenshot_region(10, 20, 100, 200, path, runner=r)
        assert "-R" in r.calls[0]
        assert "10,20,100,200" in r.calls[0]


def test_run_applescript_returns_output():
    r = FakeRunner(0, "hello\n", "")
    res = tools.run_applescript('return "hello"', runner=r)
    assert res == {"ok": True, "output": "hello"}


def test_timeout_maps_to_structured_error():
    r = FakeRunner(-1, "", "timed out after 15s (likely a pending TCC permission prompt)")
    res = tools.list_windows(runner=r)
    assert res["ok"] is False
    assert res["error"] == "timeout"
    assert "doctor" in res["hint"]


def test_notify_success():
    r = FakeRunner(0, "", "")
    res = tools.notify("Hermes", "done", runner=r)
    assert res == {"ok": True, "notified": True}
    assert "display notification" in r.calls[0][2]


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
