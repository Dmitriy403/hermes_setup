"""`hermes run` — launch Claude, optionally wrapped in the Layer B sandbox.

If Layer B is enabled (``permissions.yaml: security.layer_b.enabled: true``)
or ``--with-sandbox=PATH`` is passed, exec ``sandbox-exec -f <profile> claude
<args>``. Otherwise exec ``claude`` directly. The profile is generated from
the manifest on demand if it does not yet exist.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from shutil import which

from . import paths
from .doctor import probe as doctor_probe
from .install import sandbox_profile


def _split_args(argv: list[str]) -> tuple[str | None, list[str]]:
    """Pull out --with-sandbox=PATH; everything else is forwarded to claude."""
    with_sandbox = None
    forwarded: list[str] = []
    for a in argv:
        if a.startswith("--with-sandbox="):
            with_sandbox = a.split("=", 1)[1]
        else:
            forwarded.append(a)
    return with_sandbox, forwarded


def _ensure_profile(profile_path: str) -> None:
    p = Path(os.path.expanduser(profile_path))
    if p.exists():
        return
    p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    content = sandbox_profile.generate_from_manifest()
    p.write_text(content)
    os.chmod(p, 0o600)
    print(f"hermes run: generated sandbox profile at {p}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    with_sandbox, forwarded = _split_args(argv)

    claude = which("claude")
    if not claude:
        print("hermes run: 'claude' not found on PATH.", file=sys.stderr)
        return 127

    exp = doctor_probe.expectations(with_sandbox=with_sandbox)
    if not exp.layer_b.enabled:
        print("hermes run: Layer B disabled — launching claude directly.", file=sys.stderr)
        os.execv(claude, [claude, *forwarded])
        return 0  # unreachable

    profile = exp.layer_b.profile_path
    _ensure_profile(profile)

    sandbox_exec = which("sandbox-exec") or "/usr/bin/sandbox-exec"
    cmd = [sandbox_exec, "-f", os.path.expanduser(profile), claude, *forwarded]
    print(f"hermes run: launching under sandbox-exec ({profile})", file=sys.stderr)
    os.environ["HERMES_SANDBOX_PROFILE"] = os.path.expanduser(profile)
    os.execv(sandbox_exec, cmd)
    return 0  # unreachable


if __name__ == "__main__":
    raise SystemExit(main())
