"""--mdm-profile: emit a PPPC .mobileconfig payload.

Apple does not officially document which TCC categories are grantable via
PPPC, and the set shifts between macOS versions. v1 covers the widely
supported categories (Accessibility, Automation, Files & Folders) and
explicitly lists the others as manual-grant-only.
"""

from __future__ import annotations

import plistlib
import uuid
from typing import Any

# PPPC-supported services -> Apple PPPC key.
_PPPC_SERVICES = {
    "accessibility": "Accessibility",
    "automation": "AppleEvents",
    "files": "SystemPolicyDocumentsFolder",
}

# Categories that cannot be auto-granted via PPPC even with user-approved MDM.
_MANUAL_ONLY = ("screen_recording", "full_disk_access")


def build_mobileconfig(bundle_id: str, code_requirement: str | None = None) -> tuple[str, list[str]]:
    """Return (mobileconfig_xml, manual_only_notes).

    `bundle_id` is the responsible app's bundle id (e.g. the terminal). The
    PPPC payload authorizes that app for the supported services.
    """
    services: dict[str, Any] = {}
    for _, pppc_key in _PPPC_SERVICES.items():
        entry = {
            "Identifier": bundle_id,
            "IdentifierType": "bundleID",
            "Authorization": "Allow",
        }
        if code_requirement:
            entry["CodeRequirement"] = code_requirement
        services.setdefault(pppc_key, []).append(entry)

    payload = {
        "PayloadType": "com.apple.TCC.configuration-profile-policy",
        "PayloadIdentifier": f"org.hermes.pppc.{uuid.uuid4()}",
        "PayloadUUID": str(uuid.uuid4()).upper(),
        "PayloadVersion": 1,
        "PayloadDisplayName": "Hermes PPPC",
        "Services": services,
    }
    top = {
        "PayloadType": "Configuration",
        "PayloadIdentifier": f"org.hermes.config.{uuid.uuid4()}",
        "PayloadUUID": str(uuid.uuid4()).upper(),
        "PayloadVersion": 1,
        "PayloadDisplayName": "Hermes TCC (PPPC)",
        "PayloadContent": [payload],
    }
    xml = plistlib.dumps(top, fmt=plistlib.FMT_XML).decode("utf-8")
    notes = [
        f"{cat} cannot be granted via MDM/PPPC — grant manually in System Settings."
        for cat in _MANUAL_ONLY
    ]
    return xml, notes
