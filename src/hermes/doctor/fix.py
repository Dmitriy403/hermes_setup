"""--fix (open Settings panes) and --suggest-sandbox-patch (emit a diff)."""

from __future__ import annotations

import difflib
import subprocess
from pathlib import Path

from . import settings_urls
from .classify import Item
from .report import profile_gap

_NEEDS_FIX = {"REBUILD_DETECTED", "TERMINAL_SWAP", "REVOKED_OR_NEVER", "TCC_DENIED", "BOTH_BLOCKED"}


def run_fix(items: list[Item], *, input_fn=input) -> None:
    """Sequentially open the System Settings pane for each fixable category."""
    todo = [it for it in items if it.required and it.classification in _NEEDS_FIX]
    seen_urls: set[str] = set()
    if not todo:
        print("Nothing to fix — all required permissions are in order.")
        return

    print(f"{len(todo)} categories need attention. Opening System Settings for each.\n")
    for it in todo:
        url = settings_urls.settings_url(it.base)
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        print(f"→ {settings_urls.label(it.base)}")
        print(f"  {url}")
        try:
            subprocess.run(["open", url], check=False)
        except OSError as exc:
            print(f"  (could not open automatically: {exc})")
        try:
            input_fn("  Grant access, then press Enter to continue...")
        except (EOFError, KeyboardInterrupt):
            print("\n  Aborted.")
            return
    print("\nDone. Re-run `hermes doctor` to confirm.")


# ---- --suggest-sandbox-patch ----


def _insert_rule(lines: list[str], rule: str) -> list[str]:
    """Return new lines with `rule` inserted in a deterministic place."""
    if any(line.strip() == rule for line in lines):
        return lines  # already present

    def anchor_predicate(rule: str):
        if "mach-lookup" in rule:
            return lambda ln: "mach-lookup" in ln
        if "appleevent-send" in rule:
            return lambda ln: "appleevent-send" in ln
        if "file-read" in rule or "file-write" in rule:
            return lambda ln: "file-read" in ln or "file-write" in ln
        return None

    pred = anchor_predicate(rule)
    insert_at = None
    if pred:
        for idx, line in enumerate(lines):
            if pred(line):
                insert_at = idx + 1  # after the last matching line
    if insert_at is None:
        # No anchor — append at end.
        return lines + [rule]
    return lines[:insert_at] + [rule] + lines[insert_at:]


def suggest_patch(items: list[Item], profile_path: str) -> str:
    """Produce a unified diff that adds the missing rules to the profile.

    Returns the diff text, or an empty string if there is nothing to add.
    """
    path = Path(profile_path)
    if path.exists():
        original = path.read_text().splitlines()
    else:
        original = [
            "(version 1)",
            "(deny default)",
            '(import "/System/Library/Sandbox/Profiles/system.sb")',
        ]

    gap = profile_gap(items)
    missing = [rule for rule, _ in gap if not any(ln.strip() == rule for ln in original)]
    if not missing:
        return ""

    patched = list(original)
    for rule in missing:
        patched = _insert_rule(patched, rule)

    diff = difflib.unified_diff(
        [l + "\n" for l in original],
        [l + "\n" for l in patched],
        fromfile=profile_path,
        tofile=profile_path,
        lineterm="\n",
    )
    return "".join(diff)
