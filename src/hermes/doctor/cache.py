"""Probe cache at ``~/.hermes/probe-cache.json`` (schema v1).

Records the last-seen probe identity (cdhash, bundle id), the responsible
process the grants were observed against, per-category grant state, and a
bounded history ring buffer. Writes are atomic (temp file + rename).
A corrupt cache is backed up and recreated rather than aborting the run.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "https://hermes/probe-cache/v1"
HISTORY_MAX = 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _empty() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "updated_at": _now(),
        "probe": {},
        "responsible_process_at_grant": {},
        "grants": {},
        "history": [],
    }


class Cache:
    """Mutable in-memory view of probe-cache.json with atomic persistence."""

    def __init__(self, path: Path, data: dict[str, Any]):
        self.path = path
        self.data = data

    # ---- load / save ----

    @classmethod
    def load(cls, path: Path) -> tuple["Cache", str | None]:
        """Load the cache; on corruption back up and start fresh.

        Returns (cache, warning) where warning is non-None if the prior file
        was unreadable and got backed up.
        """
        if not path.exists():
            return cls(path, _empty()), None

        try:
            raw = json.loads(path.read_text())
            if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
                raise ValueError(f"unexpected schema: {raw.get('schema') if isinstance(raw, dict) else type(raw)}")
            # Ensure required top-level keys exist.
            for key in ("probe", "responsible_process_at_grant", "grants", "history"):
                raw.setdefault(key, [] if key == "history" else {})
            return cls(path, raw), None
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            backup = path.with_name(
                f"probe-cache.broken-{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%S')}.json"
            )
            try:
                path.rename(backup)
            except OSError:
                backup = None
            warn = (
                f"probe-cache.json was unreadable ({exc}); "
                + (f"backed up to {backup.name}; " if backup else "")
                + "starting fresh."
            )
            return cls(path, _empty()), warn

    def save(self) -> None:
        """Atomically write the cache with mode 0600."""
        self.data["updated_at"] = _now()
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), prefix=".probe-cache.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(self.data, fh, indent=2, sort_keys=True)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # ---- probe identity ----

    def probe_cdhash(self) -> str | None:
        return self.data.get("probe", {}).get("cdhash")

    def probe_binary_path(self) -> str | None:
        return self.data.get("probe", {}).get("binary_path")

    def update_probe_identity(self, cdhash: str | None, bundle_id: str, binary_path: str) -> None:
        probe = self.data.setdefault("probe", {})
        if not probe.get("first_seen"):
            probe["first_seen"] = _now()
        probe["cdhash"] = cdhash
        probe["bundle_id"] = bundle_id
        probe["binary_path"] = binary_path
        probe["last_seen"] = _now()

    # ---- responsible process ----

    def responsible_bundle(self) -> str | None:
        return self.data.get("responsible_process_at_grant", {}).get("bundle_id")

    def update_responsible(self, bundle_id: str | None, name: str | None) -> None:
        rp = self.data.setdefault("responsible_process_at_grant", {})
        if rp.get("bundle_id") != bundle_id:
            rp["bundle_id"] = bundle_id
            rp["name"] = name
            rp["first_seen_with_this_bundle"] = _now()

    # ---- grants ----

    def grant(self, category: str) -> dict[str, Any] | None:
        return self.data.get("grants", {}).get(category)

    def record_grant(self, category: str, cdhash: str | None, bundle_id: str | None) -> None:
        grants = self.data.setdefault("grants", {})
        existing = grants.get(category, {})
        grants[category] = {
            "status": "granted",
            "granted_for_cdhash": cdhash,
            "granted_for_bundle": bundle_id,
            "first_observed": existing.get("first_observed") or _now(),
            "last_verified": _now(),
        }

    def mark_not_granted(self, category: str) -> None:
        grants = self.data.setdefault("grants", {})
        entry = grants.setdefault(category, {})
        entry["status"] = "not_granted"
        entry["last_verified"] = _now()

    # ---- history ring buffer ----

    def append_history(self, event: dict[str, Any]) -> None:
        event = {**event, "at": _now()}
        hist = self.data.setdefault("history", [])
        hist.append(event)
        if len(hist) > HISTORY_MAX:
            del hist[: len(hist) - HISTORY_MAX]
