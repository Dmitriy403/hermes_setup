"""State classification.

Two classifiers:
  * three-axis (baseline-only): OK / REBUILD_DETECTED / TERMINAL_SWAP /
    REVOKED_OR_NEVER / FIRST_TIME_SEEN — compares the live probe against the
    cache to explain *why* a permission is missing.
  * differential 2x2 (Layer B): ALL_OK / SANDBOX_BLOCKED / TCC_DENIED /
    BOTH_BLOCKED / ANOMALY — compares the baseline pass against the
    sandboxed pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import settings_urls
from .cache import Cache

_SIMPLE = (
    "screen_recording",
    "accessibility",
    "full_disk_access",
    "microphone",
    "camera",
    "input_monitoring",
)


@dataclass
class Item:
    key: str               # "screen_recording" or "automation:com.apple.finder"
    base: str              # base category for deep-links: "automation"
    label: str
    baseline_status: str
    required: bool
    classification: str = "UNKNOWN"
    sandboxed_status: str | None = None
    required_sandbox_rules: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)


def flatten(probe_json: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Flatten the probe's `probes` block into key -> info."""
    probes = probe_json.get("probes", {})
    out: dict[str, dict[str, Any]] = {}

    for cat in _SIMPLE:
        p = probes.get(cat, {}) or {}
        out[cat] = {
            "status": p.get("status", "unknown"),
            "base": cat,
            "label": settings_urls.label(cat),
            "rules": p.get("required_sandbox_rules") or [],
        }

    auto = probes.get("automation", {}) or {}
    for target in auto.get("targets", []) or []:
        bid = target.get("bundle_id", "?")
        out[f"automation:{bid}"] = {
            "status": target.get("status", "unknown"),
            "base": "automation",
            "label": f"Automation → {bid}",
            "rules": target.get("required_sandbox_rules") or [],
        }

    for entry in probes.get("files", []) or []:
        path = entry.get("path", "?")
        out[f"files:{path}"] = {
            "status": entry.get("status", "unknown"),
            "base": "files",
            "label": f"Files → {path}",
            "rules": entry.get("required_sandbox_rules") or [],
        }

    return out


def _required(base: str, required_categories: set[str]) -> bool:
    return base in required_categories


def classify_baseline(
    probe_json: dict[str, Any],
    cache: Cache,
    required_categories: set[str],
) -> list[Item]:
    """Three-axis classification; mutates cache grants + history."""
    probe_cdhash = probe_json.get("self", {}).get("cdhash")
    responsible_bundle = probe_json.get("responsible_process", {}).get("bundle_id")
    flat = flatten(probe_json)
    items: list[Item] = []

    for key, info in flat.items():
        base = info["base"]
        status = info["status"]
        required = _required(base, required_categories)
        item = Item(key=key, base=base, label=info["label"],
                    baseline_status=status, required=required)
        grant = cache.grant(key)

        if status == "granted":
            if grant is None:
                item.classification = "FIRST_TIME_SEEN"
            else:
                item.classification = "OK"
            cache.record_grant(key, probe_cdhash, responsible_bundle)
        elif status in ("not_determined", "app_not_running"):
            # Not actionable as denied; surface verbatim.
            item.classification = status.upper()
            cache.mark_not_granted(key)
        else:  # denied / unknown / blocked
            if grant and grant.get("status") == "granted":
                gc = grant.get("granted_for_cdhash")
                gb = grant.get("granted_for_bundle")
                if gc != probe_cdhash:
                    item.classification = "REBUILD_DETECTED"
                    item.detail = {"from_cdhash": gc, "to_cdhash": probe_cdhash}
                    cache.append_history({"event": "cdhash_changed", "from": gc, "to": probe_cdhash})
                elif gb != responsible_bundle:
                    item.classification = "TERMINAL_SWAP"
                    item.detail = {"from_bundle": gb, "to_bundle": responsible_bundle}
                    cache.append_history(
                        {"event": "responsible_bundle_changed", "from": gb, "to": responsible_bundle}
                    )
                else:
                    item.classification = "REVOKED_OR_NEVER"
            else:
                item.classification = "REVOKED_OR_NEVER"
            cache.mark_not_granted(key)

        items.append(item)

    cache.update_probe_identity(
        probe_cdhash,
        probe_json.get("self", {}).get("bundle_id", "org.hermes.probe-tcc"),
        probe_json.get("self", {}).get("binary_path", ""),
    )
    cache.update_responsible(responsible_bundle, probe_json.get("responsible_process", {}).get("name"))
    return items


def classify_differential(
    baseline_json: dict[str, Any],
    sandboxed_json: dict[str, Any],
    required_categories: set[str],
) -> list[Item]:
    """2x2 matrix classification between baseline and sandboxed passes."""
    base_flat = flatten(baseline_json)
    sand_flat = flatten(sandboxed_json)
    items: list[Item] = []

    for key, binfo in base_flat.items():
        base = binfo["base"]
        b_status = binfo["status"]
        s = sand_flat.get(key, {})
        s_status = s.get("status", "unknown")
        rules = s.get("rules") or []

        item = Item(
            key=key, base=base, label=binfo["label"],
            baseline_status=b_status, sandboxed_status=s_status,
            required=_required(base, required_categories),
            required_sandbox_rules=rules,
        )

        b_granted = b_status == "granted"
        s_granted = s_status == "granted"
        s_blocked = s_status in ("blocked_by_sandbox", "denied")

        if b_granted and s_granted:
            item.classification = "ALL_OK"
        elif b_granted and s_blocked:
            item.classification = "SANDBOX_BLOCKED"
        elif not b_granted and s_blocked:
            item.classification = "BOTH_BLOCKED"
        elif not b_granted and s_granted:
            item.classification = "ANOMALY"
            item.detail = {
                "baseline_responsible": baseline_json.get("responsible_process", {}).get("bundle_id"),
                "sandboxed_responsible": sandboxed_json.get("responsible_process", {}).get("bundle_id"),
            }
        else:
            item.classification = b_status.upper()

        items.append(item)

    return items


# Exit-code mapping --------------------------------------------------------

_BASELINE_BAD = {"REBUILD_DETECTED", "TERMINAL_SWAP", "REVOKED_OR_NEVER"}
_MISALIGN = {"TERMINAL_SWAP"}


def baseline_exit_code(items: list[Item], strict: bool) -> int:
    code = 0
    for it in items:
        if not it.required:
            continue
        if it.classification == "OK" or it.classification == "FIRST_TIME_SEEN":
            continue
        if it.classification in _MISALIGN:
            code = max(code, 2 if strict else 1)
        elif it.classification in _BASELINE_BAD:
            code = max(code, 2)
    return code


def differential_exit_code(items: list[Item]) -> int:
    code = 0
    for it in items:
        if it.classification == "ANOMALY":
            return 10
        if it.classification in ("SANDBOX_BLOCKED", "BOTH_BLOCKED"):
            code = max(code, 3)
        elif it.classification in ("TCC_DENIED",) and it.required:
            code = max(code, 2)
    return code
