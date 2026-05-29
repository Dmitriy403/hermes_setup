"""macOS automation primitives — testable, no MCP dependency.

Every tool returns a structured dict: ``{"ok": True, ...}`` on success, or
``{"ok": False, "error": "missing_permission", "needed": ..., "how_to_fix": ...}``
when a TCC permission is missing (per the plugin-macos-control spec).

All shell-outs go through an injectable ``runner`` so the logic is unit-testable
without invoking real osascript/screencapture.
"""

from __future__ import annotations

import subprocess
from typing import Any, Callable

# runner(cmd: list[str]) -> (returncode, stdout, stderr)
Runner = Callable[[list[str]], "tuple[int, str, str]"]

_PREF = "x-apple.systempreferences:com.apple.preference.security"
_SETTINGS = {
    "Automation": f"{_PREF}?Privacy_Automation",
    "Accessibility": f"{_PREF}?Privacy_Accessibility",
    "Screen Recording": f"{_PREF}?Privacy_ScreenCapture",
}


_TIMEOUT_S = 15


def _default_runner(cmd: list[str]) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        # A hung osascript usually means a TCC prompt is pending that cannot be
        # answered in this context (e.g. Accessibility not yet granted to the
        # responsible app). Surface it rather than blocking forever.
        return -1, "", f"timed out after {_TIMEOUT_S}s (likely a pending TCC permission prompt)"
    return p.returncode, p.stdout, p.stderr


def _missing_permission(needed: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": "missing_permission",
        "needed": needed,
        "how_to_fix": _SETTINGS.get(needed, _PREF),
    }


def classify_tcc_error(stderr: str) -> str | None:
    """Map an osascript stderr to the missing TCC category, or None."""
    s = stderr.lower()
    if "-1743" in s or "not authorized to send apple events" in s or "not allowed to send" in s:
        return "Automation"
    if "-25211" in s or "assistive access" in s or "accessibility" in s:
        return "Accessibility"
    return None


def _osascript(script: str, runner: Runner) -> tuple[int, str, str]:
    return runner(["osascript", "-e", script])


def _run_osascript_tool(script: str, runner: Runner, on_ok: Callable[[str], dict]) -> dict:
    code, out, err = _osascript(script, runner)
    if code != 0:
        needed = classify_tcc_error(err)
        if needed:
            return _missing_permission(needed)
        if "timed out" in err:
            return {"ok": False, "error": "timeout", "detail": err.strip()[:300],
                    "hint": "run `hermes doctor` to check Accessibility/Automation grants"}
        return {"ok": False, "error": "osascript_failed", "detail": err.strip()[:300]}
    return on_ok(out.strip())


# ---- window / focus ----


def list_windows(runner: Runner = _default_runner) -> dict[str, Any]:
    script = (
        'tell application "System Events"\n'
        '  set out to ""\n'
        '  repeat with proc in (every process whose visible is true)\n'
        '    set pname to name of proc\n'
        '    repeat with w in (every window of proc)\n'
        '      set out to out & pname & "\t" & (name of w) & "\n"\n'
        '    end repeat\n'
        '  end repeat\n'
        '  return out\n'
        'end tell'
    )

    def parse(out: str) -> dict[str, Any]:
        windows = []
        for line in out.splitlines():
            if "\t" in line:
                app, title = line.split("\t", 1)
                windows.append({"app": app, "title": title})
        return {"ok": True, "windows": windows}

    return _run_osascript_tool(script, runner, parse)


def focus_app(app_name: str, runner: Runner = _default_runner) -> dict[str, Any]:
    script = f'tell application "{app_name}" to activate'
    return _run_osascript_tool(script, runner, lambda _: {"ok": True, "focused": app_name})


def focus_window(app_name: str, title_substring: str, runner: Runner = _default_runner) -> dict[str, Any]:
    script = (
        f'tell application "System Events" to tell process "{app_name}"\n'
        '  set frontmost to true\n'
        f'  repeat with w in (every window whose name contains "{title_substring}")\n'
        '    perform action "AXRaise" of w\n'
        '  end repeat\n'
        'end tell'
    )
    return _run_osascript_tool(script, runner, lambda _: {"ok": True, "focused": f"{app_name}:{title_substring}"})


# ---- screenshots ----
# Note: a missing Screen Recording grant does NOT make `screencapture` fail —
# it silently produces a wallpaper-only image. We cannot reliably detect that
# here; `hermes doctor` is the way to confirm the grant. We surface the path.


def _screencapture(args: list[str], path: str, runner: Runner) -> dict[str, Any]:
    code, out, err = runner(["screencapture", *args, path])
    if code != 0:
        return {"ok": False, "error": "screencapture_failed", "detail": err.strip()[:300]}
    import os
    size = os.path.getsize(path) if os.path.exists(path) else 0
    return {"ok": True, "path": path, "bytes": size,
            "note": "if blank, confirm Screen Recording via `hermes doctor`"}


def screenshot_full(path: str, runner: Runner = _default_runner) -> dict[str, Any]:
    return _screencapture(["-x"], path, runner)


def screenshot_window(window_id: int, path: str, runner: Runner = _default_runner) -> dict[str, Any]:
    return _screencapture(["-x", "-l", str(window_id)], path, runner)


def screenshot_region(x: int, y: int, w: int, h: int, path: str, runner: Runner = _default_runner) -> dict[str, Any]:
    return _screencapture(["-x", "-R", f"{x},{y},{w},{h}"], path, runner)


# ---- input / applescript / notify ----

_MODIFIER_MAP = {
    "cmd": "command down", "command": "command down",
    "shift": "shift down", "opt": "option down", "option": "option down",
    "ctrl": "control down", "control": "control down",
}


def type_text(text: str, runner: Runner = _default_runner) -> dict[str, Any]:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    script = f'tell application "System Events" to keystroke "{escaped}"'
    return _run_osascript_tool(script, runner, lambda _: {"ok": True, "typed": len(text)})


def key_combo(combo: str, runner: Runner = _default_runner) -> dict[str, Any]:
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        return {"ok": False, "error": "bad_combo", "detail": "empty combo"}
    key = parts[-1]
    mods = [_MODIFIER_MAP[m] for m in parts[:-1] if m in _MODIFIER_MAP]
    using = ""
    if mods:
        using = " using {" + ", ".join(mods) + "}"
    if len(key) == 1:
        script = f'tell application "System Events" to keystroke "{key}"{using}'
    else:
        return {"ok": False, "error": "unsupported_key",
                "detail": f"only single-character keys with modifiers supported in v1 (got '{key}')"}
    return _run_osascript_tool(script, runner, lambda _: {"ok": True, "combo": combo})


def run_applescript(script: str, runner: Runner = _default_runner) -> dict[str, Any]:
    return _run_osascript_tool(script, runner, lambda out: {"ok": True, "output": out})


def notify(title: str, message: str, runner: Runner = _default_runner) -> dict[str, Any]:
    t = title.replace('"', '\\"')
    m = message.replace('"', '\\"')
    script = f'display notification "{m}" with title "{t}"'
    return _run_osascript_tool(script, runner, lambda _: {"ok": True, "notified": True})
