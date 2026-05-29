"""System Settings deep-link URLs and tccutil category names per TCC category.

The ``x-apple.systempreferences:`` URLs open the relevant Privacy & Security
pane directly. The tccutil names are the identifiers ``tccutil reset`` accepts.
"""

from __future__ import annotations

_PREF = "x-apple.systempreferences:com.apple.preference.security"

# category -> (human label, System Settings deep-link, tccutil reset name)
_TABLE: dict[str, tuple[str, str, str | None]] = {
    "screen_recording": ("Screen Recording", f"{_PREF}?Privacy_ScreenCapture", "ScreenCapture"),
    "accessibility": ("Accessibility", f"{_PREF}?Privacy_Accessibility", "Accessibility"),
    "automation": ("Automation", f"{_PREF}?Privacy_Automation", "AppleEvents"),
    "full_disk_access": ("Full Disk Access", f"{_PREF}?Privacy_AllFiles", "SystemPolicyAllFiles"),
    "microphone": ("Microphone", f"{_PREF}?Privacy_Microphone", "Microphone"),
    "camera": ("Camera", f"{_PREF}?Privacy_Camera", "Camera"),
    "input_monitoring": ("Input Monitoring", f"{_PREF}?Privacy_ListenEvent", "ListenEvent"),
    "files": ("Files & Folders", f"{_PREF}?Privacy_Files-and-Folders", "SystemPolicyDocumentsFolder"),
}


def label(category: str) -> str:
    entry = _TABLE.get(category)
    return entry[0] if entry else category


def settings_url(category: str) -> str | None:
    entry = _TABLE.get(category)
    return entry[1] if entry else None


def tccutil_name(category: str) -> str | None:
    entry = _TABLE.get(category)
    return entry[2] if entry else None


def known_categories() -> list[str]:
    return list(_TABLE.keys())
