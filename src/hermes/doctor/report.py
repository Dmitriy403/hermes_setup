"""Human-readable and JSON rendering, plus the Layer B profile gap report."""

from __future__ import annotations

import json
from typing import Any

from . import settings_urls
from .classify import Item

_GLYPH = {
    "OK": "ok",
    "ALL_OK": "ok",
    "FIRST_TIME_SEEN": "new",
    "REBUILD_DETECTED": "rebuild",
    "TERMINAL_SWAP": "terminal-swap",
    "REVOKED_OR_NEVER": "missing",
    "SANDBOX_BLOCKED": "sandbox-blocked",
    "BOTH_BLOCKED": "both-blocked",
    "TCC_DENIED": "tcc-denied",
    "ANOMALY": "ANOMALY",
    "NOT_DETERMINED": "not-determined",
    "APP_NOT_RUNNING": "app-not-running",
}


def _fix_line(item: Item) -> str | None:
    if item.classification in ("OK", "ALL_OK", "FIRST_TIME_SEEN", "APP_NOT_RUNNING"):
        return None
    url = settings_urls.settings_url(item.base)
    if item.classification == "REBUILD_DETECTED":
        frm = item.detail.get("from_cdhash", "?")
        to = item.detail.get("to_cdhash", "?")
        return f"      probe-tcc cdhash changed: {frm} → {to} — re-grant {settings_urls.label(item.base)}: {url}"
    if item.classification == "TERMINAL_SWAP":
        frm = item.detail.get("from_bundle", "?")
        to = item.detail.get("to_bundle", "?")
        return f"      responsible bundle changed: {frm} → {to} — grant {settings_urls.label(item.base)} to the new app: {url}"
    if url:
        return f"      fix: open {url}"
    return None


def render_human(
    items: list[Item],
    probe_json: dict[str, Any],
    *,
    differential: bool,
    profile_path: str | None,
    warnings: list[str],
    exit_code: int,
) -> str:
    rp = probe_json.get("responsible_process", {})
    self_info = probe_json.get("self", {})
    lines: list[str] = []
    lines.append("Hermes doctor")
    lines.append(f"  Probe cdhash:        {self_info.get('cdhash', '<unknown>')}")
    lines.append(f"  Responsible process: {rp.get('name', '?')} (bundle: {rp.get('bundle_id', '<none>')})")
    if differential and profile_path:
        lines.append(f"  Sandbox profile:     {profile_path}")
    for w in warnings:
        lines.append(f"  ! {w}")
    lines.append("")

    col = "  Category                          Status"
    if differential:
        col += "            Sandbox"
    lines.append(col)
    lines.append("  " + "-" * (len(col) - 2))

    for it in items:
        tag = " (not required)" if not it.required else ""
        base_status = _GLYPH.get(it.classification, it.classification.lower())
        label = (it.label + tag)[:32].ljust(32)
        if differential:
            lines.append(f"  {label}  {it.baseline_status:<12}  {it.classification}")
        else:
            lines.append(f"  {label}  {base_status}")
        fix = _fix_line(it)
        if fix:
            lines.append(fix)

    # Profile gap report.
    gap = profile_gap(items)
    if gap:
        lines.append("")
        lines.append("PROFILE GAP — add these rules to your Seatbelt profile:")
        for rule, consumers in gap:
            lines.append(f"  {rule}")
            lines.append(f"      ← required by: {', '.join(consumers)}")
        lines.append("")
        lines.append("  Run `hermes doctor --suggest-sandbox-patch` for an applicable diff.")

    lines.append("")
    lines.append(f"EXIT {exit_code}")
    return "\n".join(lines)


def profile_gap(items: list[Item]) -> list[tuple[str, list[str]]]:
    """Aggregate required_sandbox_rules from blocked categories.

    Returns a list of (rule, [consumer labels]) deduplicated by rule, in
    first-seen order.
    """
    order: list[str] = []
    consumers: dict[str, list[str]] = {}
    for it in items:
        if it.classification not in ("SANDBOX_BLOCKED", "BOTH_BLOCKED"):
            continue
        for rule in it.required_sandbox_rules:
            if rule not in consumers:
                consumers[rule] = []
                order.append(rule)
            if it.label not in consumers[rule]:
                consumers[rule].append(it.label)
    return [(rule, consumers[rule]) for rule in order]


def render_json(
    items: list[Item],
    probe_json: dict[str, Any],
    *,
    differential: bool,
    profile_path: str | None,
    warnings: list[str],
    exit_code: int,
) -> str:
    payload = {
        "schema": "https://hermes/doctor/v1",
        "probe": {
            "cdhash": probe_json.get("self", {}).get("cdhash"),
            "binary_path": probe_json.get("self", {}).get("binary_path"),
        },
        "responsible_process": probe_json.get("responsible_process", {}),
        "sandbox": {
            "active": bool(differential),
            "profile_path": profile_path,
            "differential": differential,
        },
        "categories": [
            {
                "key": it.key,
                "base": it.base,
                "label": it.label,
                "required": it.required,
                "classification": it.classification,
                "baseline_status": it.baseline_status,
                "sandboxed_status": it.sandboxed_status,
                "required_sandbox_rules": it.required_sandbox_rules,
                "detail": it.detail,
                "settings_url": settings_urls.settings_url(it.base),
            }
            for it in items
        ],
        "profile_gap": [
            {"rule": rule, "consumers": consumers} for rule, consumers in profile_gap(items)
        ],
        "warnings": warnings,
        "exit_code": exit_code,
    }
    return json.dumps(payload, indent=2, sort_keys=True)
